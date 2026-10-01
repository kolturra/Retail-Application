import logging

from retail import clock, db, i18n
from retail import license as lic
from retail_ui import settings as ui_settings
from retail_ui.session import AppSession

log = logging.getLogger("retail_ui")


def bootstrap(paths, *, public_key, machine_id, request_activation, run_onboarding, today=None):
    """Open the shop database, make sure the licence is usable and the shop is set up.

    request_activation(machine_id, invalid) -> key text, or None to quit.
    run_onboarding(session) -> True when the shop was set up.
    Returns the AppSession, or None when the user quit or the app cannot be used."""
    paths.ensure()
    settings = ui_settings.load(paths.settings_path)
    backup_dir = settings.backup_dir or paths.backup_dir
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
        if not session.has_shop():
            if state.read_only or not run_onboarding(session):
                session.close()
                return None
        i18n.set_language(session.shop()["language"])
        return session
    except BaseException:
        try:
            conn.close()
        except Exception:
            pass
        raise
