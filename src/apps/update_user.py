from resources.structures.Bloxlink import Bloxlink # pylint: disable=import-error, no-name-in-module
from resources.exceptions import Error, UserNotVerified, Message, BloxlinkBypass, CancelCommand, PermissionError, Blacklisted # pylint: disable=import-error, no-name-in-module
from config import REACTIONS # pylint: disable=no-name-in-module, import-error
import discord

guild_obligations, format_update_embed = Bloxlink.get_module("roblox", attrs=["guild_obligations", "format_update_embed"])


@Bloxlink.extension
class UpdateUserExtension(Bloxlink.Module):
    """update a user's roles and nickname"""

    def __init__(self):
        self.type = 2
        self.name = "Update User"
        self.permissions = Bloxlink.Permissions().build("BLOXLINK_UPDATER")
        self.slash_defer = True
        self.slash_ephemeral = True
        self.premium_bypass_channel_perms = True

    async def __main__(self, ExtensionArgs):
        user  = ExtensionArgs.resolved
        guild = ExtensionArgs.guild

        guild_data = ExtensionArgs.guild_data
        response   = ExtensionArgs.response

        if user.bot:
            raise Error("You cannot update bots!", hidden=True)

        if isinstance(user, discord.User):
            try:
                user = await guild.fetch_member(user.id)
            except discord.errors.NotFound:
                raise Error("This user isn't in your server!")

        try:
            added, removed, nickname, errors, warnings, roblox_user = await guild_obligations(
                user,
                guild             = guild,
                guild_data        = guild_data,
                roles             = True,
                nickname          = True,
                cache             = False,
                dm                = False,
                event             = True,
                exceptions        = ("BloxlinkBypass", "Blacklisted", "CancelCommand", "UserNotVerified", "PermissionError", "RobloxDown", "RobloxAPIError"))

            await response.send(f"{REACTIONS['DONE']} **Updated** {user.mention}", hidden=True)

        except BloxlinkBypass:
            raise Message("Since this user has the Bloxlink Bypass role, I was unable to update their roles/nickname.", type="info", hidden=True)

        except Blacklisted as b:
            if isinstance(b.message, str):
                raise Error(f"{user.mention} has an active restriction for: `{b}`", hidden=True)
            else:
                raise Error(f"{user.mention} has an active restriction from Bloxlink.", hidden=True)

        except CancelCommand:
            pass

        except UserNotVerified:
            raise Error("This user is not linked to Bloxlink.", hidden=True)

        except PermissionError as e:
            raise Error(e.message, hidden=True)
