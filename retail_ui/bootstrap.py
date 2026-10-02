import logging

from retail import clock, db, i18n
from retail import license as lic
from retail_ui import settings as ui_settings
from retail_ui.session import AppSession, usable_folder

log = logging.getLogger("retail_ui")


def bootstrap(paths, *, public_key, machine_id, request_activation, run_onboarding, today=None):
    """Open the shop database, make sure the licence is usable and the shop is set up.

    request_activation(machine_id, invalid) -> key text, or None to quit.
    run_onboarding(session) -> True when the shop was set up.
    Returns the AppSession, or None when the user quit or the app cannot be used."""
    paths.ensure()
    settings = ui_settings.load(paths.settings_path)
    backup_dir = settings.backup_dir or paths.backup_dir
    if settings.backup_dir and not usable_folder(settings.backup_dir):
        # e.g. a USB drive that is gone: a pending migration's safety backup must not lock the owner out
        log.warning("configured backup folder %s is not usable; using %s", settings.backup_dir, paths.backup_dir)
        backup_dir = paths.backup_dir
    conn = db.open_shop(paths.db_path, backup_dir)
    try:
        state = lic.apply_license(paths.license_path, public_key, machine_id, today)
        invalid = False
        while state.status == "invalid":
            key = request_activation(machine_id, invalid)
            if key is None:
                conn.close()
                return None
            candidate = lic.verify_key(key, machine_id, public_key, today or clock.today())
            if candidate.status == "invalid":
                invalid = True
                continue
            lic.save_key(paths.license_path, key)
            state = lic.apply_license(paths.license_path, public_key, machine_id, today)
        session = AppSession(paths, settings, conn, state, public_key=public_key, machine_id=machine_id)
        if not session.has_shop() and not state.read_only:
            # an expired licence blocks writes, so onboarding is impossible; the owner may still restore a backup
            if not run_onboarding(session):
                session.close()
                return None
        if session.has_shop():
            i18n.set_language(session.shop()["language"])
        return session
    except BaseException:
        try:
            conn.close()
        except Exception:
            pass
        raise
