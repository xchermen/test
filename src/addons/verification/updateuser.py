from resources.structures.Bloxlink import Bloxlink # pylint: disable=import-error, no-name-in-module
from resources.exceptions import Error, UserNotVerified, Message, BloxlinkBypass, CancelCommand, PermissionError, Blacklisted # pylint: disable=import-error, no-name-in-module
from config import REACTIONS # pylint: disable=no-name-in-module
from resources.constants import RELEASE # pylint: disable=import-error, no-name-in-module
from discord import Object, Role, User
from discord.errors import NotFound
import math

guild_obligations, format_update_embed = Bloxlink.get_module("roblox", attrs=["guild_obligations", "format_update_embed"])
parse_message = Bloxlink.get_module("commands", attrs=["parse_message"])
get_features = Bloxlink.get_module("premium", attrs="get_features")


class UpdateUserCommand(Bloxlink.Module):
    """force update user(s) with roles and nicknames"""

    def __init__(self):
        permissions = Bloxlink.Permissions().build("BLOXLINK_UPDATER")
        permissions.allow_bypass = True

        self.permissions = permissions
        self.aliases = ["update", "updateroles", "update-user"]
        self.arguments = [
            {
                "prompt": "Please specify user(s) or role(s) to update. For example: `@user1 @user2 @user3` or `@role`",
                "type": ["user", "role"],
                "name": "users",
                "multiple": True,
                "optional": True,
                "guild_members_only": True,
                "create_missing_role": False
            }
        ]
        self.slash_args = [
            {
                "prompt": "Please select the user to update.",
                "name": "user",
                "type": "user",
                "optional": True
            },
            {
                "prompt": "Please select the role of members to update.",
                "name": "role",
                "type": "role",
                "optional": True
            }
        ]
        self.category = "Administration"
        self.cooldown = 2
        self.REDIS_COOLDOWN_KEY = "guild_scan:{id}"
        self.slash_enabled = True
        self.slash_defer = True

    async def __main__(self, CommandArgs):
        response = CommandArgs.response

        user_slash = CommandArgs.parsed_args.get("user")
        role_slash = CommandArgs.parsed_args.get("role")
        users_ = CommandArgs.parsed_args.get("users") or ([user_slash, role_slash] if user_slash or role_slash else None)
        prefix = CommandArgs.prefix

        message = CommandArgs.message
        author = CommandArgs.author
        guild = CommandArgs.guild

        guild_data = CommandArgs.guild_data

        users = []

        if not (users_ and CommandArgs.has_permission):
            if not users_:
                if message:
                    message.content = f"{prefix}getrole"
                    return await parse_message(message)
                else:
                    raise Message(f"To update yourself, please run the `{prefix}getrole` command.", hidden=True, type="info")
            else:
                raise Message("You do not have permission to update users; you need the `Manage Roles` permission, or "
                              "a role called `Bloxlink Updater`.", type="info", hidden=True)

        if CommandArgs.slash_command:
            if not guild.chunked:
                await guild.chunk()

            if users_[1]:
                role = users_[1]

                users += role.members

                if not users:
                    raise Error("This role has no members in it!", hidden=True)

            if users_[0]:
                user = users_[0]
                users.append(user)
        else:
            if isinstance(users_[0], Role):
                for role in users_:
                    if not role.members:
                        raise Error("This role has no members in it!", hidden=True)

                    users += role.members
            else:
                users = users_

        len_users = len(users)

        for i, user in enumerate(users):
            if isinstance(user, User):
                try:
                    user = await guild.fetch_member(user.id)
                except NotFound:
                    raise Error("This user isn't in your server!")
                else:
                    users[i] = user

        if self.redis:
            redis_cooldown_key = self.REDIS_COOLDOWN_KEY.format(release=RELEASE, id=guild.id)
            on_cooldown = await self.redis.get(redis_cooldown_key)

            if len_users > 3 and on_cooldown:
                cooldown_time = math.ceil(await self.redis.ttl(redis_cooldown_key)/60)

                if not cooldown_time or cooldown_time == -1:
                    await self.redis.delete(redis_cooldown_key)
                    on_cooldown = None

                if on_cooldown:
                    if on_cooldown == 1:
                        raise Message(f"This server is still queued.")
                    elif on_cooldown == 2:
                        raise Message("This server's scan is currently running.")
                    elif on_cooldown == 3:
                        cooldown_time = math.ceil(await self.redis.ttl(redis_cooldown_key)/60)

                        raise Message(f"This server has an ongoing cooldown! You must wait **{cooldown_time}** more minutes.")

            donator_profile, _ = await get_features(Object(id=guild.owner_id), guild=guild)
            premium = donator_profile.features.get("premium")

            if not premium:
                donator_profile, _ = await get_features(author)
                premium = donator_profile.features.get("premium")

            cooldown = 0

            if len_users > 10:
                if not premium:
                    raise Error("You need premium in order to update more than 10 members at a time! "
                                f"Use `{prefix}donate` for instructions on donating.")

                if len_users >= 100:
                    cooldown = math.ceil(((len_users / 1000) * 120) * 60)
                else:
                    cooldown = 120

                if self.redis:
                    await self.redis.set(redis_cooldown_key, 2, ex=86400)

            trello_board = CommandArgs.trello_board

            #async with response.loading():
            if len_users > 1:
                for user in users:
                    if not user.bot:
                        try:
                            added, removed, nickname, errors, warnings, roblox_user = await guild_obligations(
                                user,
                                guild             = guild,
                                guild_data        = guild_data,
                                trello_board      = trello_board,
                                roles             = True,
                                nickname          = True,
                                dm                = False,
                                exceptions        = ("BloxlinkBypass", "UserNotVerified", "Blacklisted", "PermissionError", "RobloxDown"),
                                cache             = False)
                        except BloxlinkBypass:
                            if len_users <= 10:
                                await response.info(f"{user.mention} **bypassed**")
                        except UserNotVerified:
                            if len_users <= 10:
                                await response.send(f"{REACTIONS['ERROR']} {user.mention} is **not linked to Bloxlink**")
                        except PermissionError as e:
                            raise Error(e.message)
                        except Blacklisted as b:
                            if len_users <= 10:
                                await response.send(f"{REACTIONS['ERROR']} {user.mention} has an active restriction.")
                        else:
                            if len_users <= 10:
                                await response.send(f"{REACTIONS['DONE']} **Updated** {user.mention}")
            else:
                user = users[0]

                if user.bot:
                    raise Message("Bots can't have Roblox accounts!", type="silly")

                old_nickname = user.display_name

                try:
                    added, removed, nickname, errors, warnings, roblox_user = await guild_obligations(
                        user,
                        guild             = guild,
                        guild_data        = guild_data,
                        trello_board      = trello_board,
                        roles             = True,
                        nickname          = True,
                        cache             = False,
                        dm                = False,
                        event             = True,
                        exceptions        = ("BloxlinkBypass", "Blacklisted", "CancelCommand", "UserNotVerified", "PermissionError", "RobloxDown", "RobloxAPIError"))

                    _, embed, view = await format_update_embed(roblox_user, user, added=added, removed=removed, errors=errors, warnings=warnings, nickname=nickname if old_nickname != nickname else None, prefix=prefix, guild_data=guild_data)

                    await response.send(embed=embed, view=view)

                except BloxlinkBypass:
                    raise Message("Since this user has the Bloxlink Bypass role, I was unable to update their roles/nickname.", type="info")

                except Blacklisted as b:
                    if isinstance(b.message, str):
                        raise Error(f"{user.mention} has an active restriction for: `{b}`")
                    else:
                        raise Error(f"{user.mention} has an active restriction from Bloxlink.")

                except CancelCommand:
                    pass

                except UserNotVerified:
                    raise Error("This user is not linked to Bloxlink.")

                except PermissionError as e:
                    raise Error(e.message)

            if cooldown:
                await self.redis.set(redis_cooldown_key, 3, ex=cooldown)

            if len_users > 10:
                await response.success("All users updated.")
