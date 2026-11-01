"""Integration mode is checked before restoring any platform session."""
import os


def is_live():
    return os.getenv('ALL_EXECUTION_MODE', 'preview') == 'live'


def require_live():
    if not is_live():
        raise RuntimeError('演练模式禁止建立真实闲鱼会话或执行平台动作')


def manual_verification(account_id=''):
    """Do not invoke automatic CAPTCHA solvers in the integrated distribution."""
    import cookie_manager
    if cookie_manager.manager is not None and account_id in cookie_manager.manager.cookies:
        cookie_manager.manager.update_cookie_status(account_id, False)
    raise RuntimeError('检测到验证要求：已停止自动验证，请人工处理后重新启用账号')
