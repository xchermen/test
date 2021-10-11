from resources.structures.Bloxlink import Bloxlink # pylint: disable=import-error, no-name-in-module
from resources.exceptions import Error, UserNotVerified, Message # pylint: disable=import-error, no-name-in-module

get_user, get_binds = Bloxlink.get_module("roblox", attrs=["get_user", "get_binds"])


@Bloxlink.extension
class GetInfoExtension(Bloxlink.Module):
    """update a user's roles and nickname"""

    def __init__(self):
        self.type = 2
        self.name = "Get Roblox Info"
        self.slash_defer = True
        self.slash_ephemeral = True
        self.premium_bypass_channel_perms = True

    async def __main__(self, ExtensionArgs):
        user  = ExtensionArgs.resolved
        guild = ExtensionArgs.guild

        guild_data = ExtensionArgs.guild_data
        response   = ExtensionArgs.response
        prefix     = ExtensionArgs.prefix

        if user.bot:
            raise Error("Bots cannot have Roblox accounts!", hidden=True)

        if guild:
            role_binds, group_ids, _ = await get_binds(guild_data=guild_data)
        else:
            role_binds, group_ids = {}, {}

        try:
            account, accounts = await get_user(author=user, guild=guild, group_ids=(group_ids, role_binds), send_embed=True, send_ephemeral=True, response=response, everything=True)
        except UserNotVerified:
            raise Error(f"**{user}** is not linked to Bloxlink.", hidden=True)
        else:
            if not account:
                raise Message(f"This Discord user has no primary account set! They may use `{prefix}switchuser` to set one.", type="info", hidden=True)
