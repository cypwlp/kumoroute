"""Backup and restore API methods for the Python fallback backend."""

import json
import re
import uuid
from datetime import datetime
from pathlib import Path


def install_api_methods(api_cls, app_module):
    def backup_payload(self):
        safe_keys = (
            "mixed_port", "controller_port", "mode", "vpn_disable_system_proxy",
            "vpn_restore_system_proxy", "network_mode", "force_disable_ipv6",
            "dns_mode", "subscription_update_hours", "last_subscription_update",
        )
        profiles = []
        for entry in self._profiles.entries:
            if entry.get("kind") == "builtin":
                continue
            path = self._profiles.path_of(entry["id"])
            if not path.is_file():
                raise FileNotFoundError(f"找不到配置檔案：{path}")
            profiles.append({
                "id": entry.get("id", ""), "name": entry.get("name", ""),
                "kind": entry.get("kind", "local"), "url": entry.get("url", ""),
                "updated_at": entry.get("updated_at", ""),
                "content": path.read_text(encoding="utf-8"),
            })
        return {
            "schema": 1,
            "app_version": app_module.APP_VERSION,
            "created_at": datetime.now().isoformat(),
            "settings": {key: self._store.data.get(key) for key in safe_keys if key in self._store.data},
            "active_profile": self._store.data.get("active_profile", ""),
            "profiles": profiles,
            "notice": "VPN credentials are stored separately and are not included.",
        }

    def apply_backup_payload(self, payload):
        if not isinstance(payload, dict) or payload.get("schema") != 1:
            raise ValueError("不支援的備份格式")
        profiles_data = payload.get("profiles") or []
        if not isinstance(profiles_data, list):
            raise ValueError("備份中的訂閱資料格式錯誤")
        raw_settings = payload.get("settings") or {}
        if not isinstance(raw_settings, dict):
            raise ValueError("備份中的設定格式錯誤")

        safe_keys = {
            "mode", "vpn_disable_system_proxy", "vpn_restore_system_proxy",
            "network_mode", "force_disable_ipv6", "dns_mode",
            "subscription_update_hours", "last_subscription_update",
        }
        candidate = {
            "mixed_port": self._store.data.get("mixed_port", 7890),
            "controller_port": self._store.data.get("controller_port", 9090),
        }
        for key in ("mixed_port", "controller_port"):
            if key in raw_settings:
                try:
                    candidate[key] = int(raw_settings[key])
                except (TypeError, ValueError) as exc:
                    raise ValueError(f"備份中的 {key} 格式錯誤") from exc
        if not all(1024 <= int(candidate[key]) <= 65535 for key in candidate):
            raise ValueError("備份中的連接埠必須介於 1024 與 65535")
        if candidate["mixed_port"] == candidate["controller_port"]:
            raise ValueError("備份中的混合代理與控制埠不可相同")

        validated = {}
        for key in safe_keys:
            if key not in raw_settings:
                continue
            value = raw_settings[key]
            if key in ("vpn_disable_system_proxy", "vpn_restore_system_proxy", "force_disable_ipv6"):
                if not isinstance(value, bool):
                    raise ValueError(f"備份中的 {key} 必須是布林值")
            elif key == "mode" and value not in ("rule", "global", "direct"):
                raise ValueError("備份中的代理模式無效")
            elif key == "network_mode" and value not in ("proxy", "vpn", "coexist"):
                raise ValueError("備份中的網路模式無效")
            elif key == "dns_mode" and value not in ("auto", "backup"):
                raise ValueError("備份中的 DNS 模式無效")
            elif key == "subscription_update_hours":
                try:
                    value = int(value)
                except (TypeError, ValueError) as exc:
                    raise ValueError("備份中的訂閱更新間隔格式錯誤") from exc
                if value not in (0, 6, 12, 24):
                    raise ValueError("備份中的訂閱更新間隔無效")
            elif key == "last_subscription_update":
                value = str(value or "")
                if value:
                    try:
                        datetime.fromisoformat(value)
                    except ValueError as exc:
                        raise ValueError("備份中的訂閱更新時間格式錯誤") from exc
            validated[key] = value

        builtin = [entry for entry in self._profiles.entries if entry.get("kind") == "builtin"]
        restored = []
        staged = []
        used_ids = {entry.get("id") for entry in builtin}
        for item in profiles_data:
            if not isinstance(item, dict) or not item.get("content"):
                continue
            content = str(item["content"])
            app_module.Profiles._validate(content)
            pid = str(item.get("id") or "")
            if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", pid) or pid in used_ids:
                pid = uuid.uuid4().hex[:8]
            used_ids.add(pid)
            kind = "remote" if item.get("kind") == "remote" else "local"
            url = str(item.get("url") or "")
            if kind == "remote":
                if not url:
                    raise ValueError("遠端訂閱缺少網址")
                app_module.Profiles._validate_remote_url(url)
            entry = {
                "id": pid,
                "name": str(item.get("name") or pid)[:128],
                "kind": kind,
                "url": url,
                "updated_at": str(item.get("updated_at") or app_module._now()),
            }
            restored.append(entry)
            staged.append((self._profiles.path_of(pid), content))

        active = str(payload.get("active_profile") or "")
        if active not in {entry["id"] for entry in restored}:
            active = restored[0]["id"] if restored else (builtin[0]["id"] if builtin else "")

        for key in ("mixed_port", "controller_port"):
            self._store.data[key] = candidate[key]
        self._store.data.update(validated)
        for path, content in staged:
            app_module._atomic_write_text(path, content)
        self._profiles.entries = builtin + restored
        self._store.data["active_profile"] = active
        self._profiles._save()
        self._store.save()

    def export_backup(self):
        try:
            folder = Path.home() / "Downloads"
            if not folder.is_dir():
                folder = app_module.data_dir()
            folder.mkdir(parents=True, exist_ok=True)
            path = folder / f"KumoRoute-backup-{datetime.now():%Y%m%d-%H%M%S-%f}.json"
            app_module._atomic_write_text(path, json.dumps(backup_payload(self), ensure_ascii=False, indent=2))
            return {"ok": True, "path": str(path)}
        except Exception as exc:
            return {"ok": False, "error": f"建立備份失敗：{exc}"}

    def import_backup(self):
        try:
            res = self._win.create_file_dialog(
                app_module.webview.OPEN_DIALOG,
                allow_multiple=False,
                file_types=("KumoRoute 備份 (*.json)", "所有檔案 (*.*)"),
            )
            if not res:
                return {"ok": False, "cancelled": True}
            src = res[0] if isinstance(res, (list, tuple)) else res
            payload = json.loads(Path(src).read_text(encoding="utf-8"))
            if payload.get("schema") != 1:
                return {"ok": False, "error": "不支援的備份格式"}
            safety = backup_payload(self)
            safety_path = app_module.data_dir() / "backups" / f"pre-restore-{datetime.now():%Y%m%d-%H%M%S-%f}.json"
            safety_path.parent.mkdir(parents=True, exist_ok=True)
            app_module._atomic_write_text(safety_path, json.dumps(safety, ensure_ascii=False, indent=2))
            try:
                apply_backup_payload(self, payload)
                ok, message = self._core.reload_runtime()
                if not ok:
                    raise ValueError(message)
            except Exception:
                apply_backup_payload(self, safety)
                raise
            return {"ok": True, "path": str(src), "safety_backup": str(safety_path), "profiles": len(payload.get("profiles") or [])}
        except Exception as exc:
            return {"ok": False, "error": f"還原備份失敗：{exc}"}

    api_cls._backup_payload = backup_payload
    api_cls._apply_backup_payload = apply_backup_payload
    api_cls.export_backup = export_backup
    api_cls.import_backup = import_backup
