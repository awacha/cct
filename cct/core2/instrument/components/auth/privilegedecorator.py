from typing import Optional

from .privilege import Privilege
from .usermanager import UserManager


def needsprivilege(privilege: Privilege, errormessage: Optional[str] = None):
    def decorator(function):
        def func(*args, **kwargs):
            if not UserManager.instance.hasPrivilege(privilege):
                raise RuntimeError(
                    f'Privilege {privilege} required to run this function' if errormessage is None else errormessage)
            else:
                return function(*args, **kwargs)

        return func

    return decorator
