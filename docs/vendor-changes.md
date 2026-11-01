# Vendor changes

Pinned source: GuDong2003/xianyu-auto-reply-fix @ 8ae4544.

- all_runtime.py, Start.py, cookie_manager.py: fail-closed preview gate before restoring any real account listener.
- reply_server.py: preview rejects seller routes and reports isolated health; live retains conditional relist only, without optional polishing/rate/flower background schedulers.
- Runtime databases are separated by mode in root Compose.

Use the root Compose, not the vendor's standalone Compose. The vendor snapshot is not independently advertised as the integrated application.
- Internal service login: dedicated token plus the seller administrator password; does not depend on the interactive management-login CAPTCHA.
- slider_orchestrator and XianyuSliderStealth entry points reject automatic verification and request manual handling; known manager accounts are disabled on that path.

- all_runtime.py / auto_relist_task.py / reply_server.py: authenticated persistent dispatch pause, checked before relist work and before staging a new publish. In-flight calls are not recalled.
