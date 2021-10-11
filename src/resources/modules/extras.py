from ..structures.Bloxlink import Bloxlink # pylint: disable=import-error, no-name-in-module
from ..constants import MAGIC_ROLES # pylint: disable=import-error, no-name-in-module
import discord


@Bloxlink.module
class Extras(Bloxlink.Module):
    def __init__(self):
        pass

    def has_magic_role(self, author, magic_roles_data, magic_role_name=None):
        has_any_magic_role = False
        magic_roles_data = magic_roles_data or {}

        for role in author.roles:
            if role.name == magic_role_name:
                has_any_magic_role = True
                return True
            else:
                if role.name in MAGIC_ROLES:
                    has_any_magic_role = True

        users_magic_roles = filter(lambda rd: author.get_role(int(rd[0])), magic_roles_data.items())

        if not magic_role_name:
            return bool(users_magic_roles) or has_any_magic_role

        for magic_role in users_magic_roles:
            if magic_role_name in magic_role[1]:
                return True
