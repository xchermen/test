from ..structures.Bloxlink import Bloxlink # pylint: disable=no-name-in-module, import-error
from ..exceptions import (BadUsage, RobloxAPIError, Error, CancelCommand, UserNotVerified,# pylint: disable=no-name-in-module, import-error
                           RobloxNotFound, PermissionError, BloxlinkBypass, RobloxDown, Blacklisted)
from typing import Tuple
import discord
from datetime import datetime
from ratelimit import limits, RateLimitException
from backoff import on_exception, expo
from config import REACTIONS, PREFIX # pylint: disable=import-error, no-name-in-module
from ..constants import (RELEASE, DEFAULTS, ORANGE_COLOR, PARTNERED_SERVER, ARROW, # pylint: disable=import-error, no-name-in-module
                         SERVER_INVITE, PURPLE_COLOR, PINK_COLOR, PARTNERS_COLOR, GREEN_COLOR, # pylint: disable=import-error, no-name-in-module
                         RED_COLOR, ACCOUNT_SETTINGS_URL, TRELLO, SELF_HOST, EMBED_PERKS,
                         VERIFY_URL) # pylint: disable=import-error, no-name-in-module
import json
import random
import re
import asyncio
import dateutil.parser as parser
import math
import traceback


nickname_template_regex = re.compile(r"\{(.*?)\}")
trello_card_bind_regex = re.compile(r"(.*?): ?(.*)")
any_group_nickname = re.compile(r"\{group-rank-(.*?)\}")
bracket_search = re.compile(r"\[(.*)\]")
roblox_group_regex = re.compile(r"roblox.com/groups/(\d+)/")


loop = asyncio.get_event_loop()

fetch, post_event = Bloxlink.get_module("utils", attrs=["fetch", "post_event"])
get_features = Bloxlink.get_module("premium", attrs=["get_features"])
get_options, get_board = Bloxlink.get_module("trello", attrs=["get_options", "get_board"])
cache_set, cache_get, cache_pop, get_guild_value = Bloxlink.get_module("cache", attrs=["set", "get", "pop", "get_guild_value"])
get_restriction = Bloxlink.get_module("blacklist", attrs=["get_restriction"])
has_magic_role = Bloxlink.get_module("extras", attrs=["has_magic_role"])


API_URL = "https://api.roblox.com"
BASE_URL = "https://www.roblox.com"
GROUP_API = "https://groups.roblox.com"
THUMBNAIL_API = "https://thumbnails.roblox.com"

BIND_ROLE_BUG = "https://cdn.discordapp.com/attachments/385984496723427328/386636215404855297/bloxrolebug.gif"



@Bloxlink.module
class Roblox(Bloxlink.Module):
    def __init__(self):
        self.pending_verifications = {}

    @staticmethod
    async def get_roblox_id(username) -> Tuple[str, str]:
        username_lower = username.lower()
        roblox_cached_data = await cache_get(f"usernames_to_ids:{username_lower}")

        if roblox_cached_data:
            return roblox_cached_data

        json_data, response = await fetch(f"{API_URL}/users/get-by-username/?username={username}", json=True, raise_on_failure=True)

        if json_data.get("success") is False:
            raise RobloxNotFound

        correct_username, roblox_id = json_data.get("Username"), str(json_data.get("Id"))

        data = (roblox_id, correct_username)

        if correct_username:
            await cache_set(f"usernames_to_ids:{username_lower}", data)

        return data

    @staticmethod
    async def get_roblox_username(roblox_id) -> Tuple[str, str]:
        roblox_user = await cache_get(f"roblox_users:{roblox_id}")

        if roblox_user and roblox_user.verified:
            return roblox_user.id, roblox_user.username

        json_data, response = await fetch(f"{API_URL}/users/{roblox_id}", json=True, raise_on_failure=True)

        if json_data.get("success") is False:
            raise RobloxNotFound

        correct_username, roblox_id = json_data.get("Username"), str(json_data.get("Id"))

        data = (roblox_id, correct_username)

        return data

    @staticmethod
    async def validate_code(roblox_id, code):
        if RELEASE == "LOCAL":
            return True

        try:
            html_text, _ = await fetch(f"https://www.roblox.com/users/{roblox_id}/profile", raise_on_failure=True)
        except RobloxNotFound:
            raise Error("You cannot link as a banned user. Please try again with another user.")

        return code in html_text


    async def parse_accounts(self, accounts, reverse_search=False):
        parsed_accounts = {}

        for account in accounts:
            roblox_user = RobloxUser(roblox_id=account)
            await roblox_user.sync()

            if reverse_search:
                discord_ids = (await self.r.db("bloxlink").table("robloxAccounts").get(account).run() or {}).get("discordIDs") or []
                discord_accounts = []

                for discord_id in discord_ids:
                    try:
                        user = await Bloxlink.fetch_user(int(discord_id))
                    except discord.errors.NotFound:
                        pass
                    else:
                        discord_accounts.append(user)

                parsed_accounts[roblox_user.username] = (roblox_user, discord_accounts)

            else:
                parsed_accounts[roblox_user.username] = roblox_user

        return parsed_accounts

    @staticmethod
    def count_binds(guild_data, role_binds=None, group_ids=None):
        guild_data = guild_data or {}

        role_binds = role_binds or guild_data.get("roleBinds", {})
        group_ids = group_ids or guild_data.get("groupIDs", {})

        bind_count = 0

        for bind_category, binds in role_binds.items():
            for bind_id, bind_data in binds.items():
                if bind_data:
                    if bind_category == "groups":
                        bind_count += len(bind_data.get("binds", {})) + len(bind_data.get("ranges", {}))
                    else:
                        bind_count += 1

        bind_count += len(group_ids)

        return bind_count


    async def extract_accounts(self, user_data, resolve_to_users=True, reverse_search=False):
        roblox_ids = {}

        primary_account = user_data.get("robloxID")
        if primary_account:
            roblox_ids[primary_account] = True

        for roblox_id in user_data.get("robloxAccounts", {}).get("accounts", []):
            roblox_ids[roblox_id] = True

        if reverse_search:
            for roblox_id in roblox_ids.keys():
                discord_ids = (await self.r.db("bloxlink").table("robloxAccounts").get(roblox_id).run() or {}).get("discordIDs") or []
                discord_accounts = []

                if resolve_to_users:
                    for discord_id in discord_ids:
                        try:
                            user = await Bloxlink.fetch_user(int(discord_id))
                        except discord.errors.NotFound:
                            pass
                        else:
                            discord_accounts.append(user)
                else:
                    discord_accounts = discord_ids

                roblox_ids[roblox_id] = discord_accounts

            return roblox_ids
        else:
            return list(roblox_ids.keys())


    async def verify_member(self, author, roblox, guild=None, author_data=None, primary_account=False, allow_reverify=True):
        # TODO: make this insert a new DiscordProfile or append the account to it
        author_id = str(author.id)
        guild = guild or getattr(author, "guild", None)
        guild_id = guild and str(guild.id)

        if isinstance(roblox, RobloxUser):
            roblox_id = str(roblox.id)
        else:
            roblox_id = str(roblox)

        author_data = author_data or await self.r.db("bloxlink").table("users").get(author_id).run() or {}
        roblox_accounts = author_data.get("robloxAccounts", {})
        roblox_list = roblox_accounts.get("accounts", [])

        if guild:
            guild_list = roblox_accounts.get("guilds", {})
            guild_find = guild_list.get(guild_id)

            if guild_find and not allow_reverify and guild_find != roblox:
                raise Error("You already selected your account for this server! `allowReVerify` must be enabled for you to change your account.")

            guild_list[guild_id] = roblox_id
            roblox_accounts["guilds"] = guild_list


        if not roblox_id in roblox_list:
            roblox_list.append(roblox_id)
            roblox_accounts["accounts"] = roblox_list


        roblox_discord_data = await self.r.db("bloxlink").table("robloxAccounts").get(roblox_id).run() or {"id": roblox_id}
        discord_ids = roblox_discord_data.get("discordIDs") or []

        if author_id not in discord_ids:
            discord_ids.append(author_id)
            roblox_discord_data["discordIDs"] = discord_ids

            await self.r.db("bloxlink").table("robloxAccounts").insert(roblox_discord_data, conflict="update").run()


        await self.r.db("bloxlink").table("users").insert(
            {
                "id": author_id,
                "robloxID": primary_account and roblox_id or author_data.get("robloxID"),
                "robloxAccounts": roblox_accounts
            },
            conflict="update"
        ).run()

        await cache_pop(f"discord_profiles:{author_id}")

    async def unverify_member(self, author, roblox):
        author_id = str(author.id)
        success = False

        if isinstance(roblox, RobloxUser):
            roblox_id = str(roblox.id)
        else:
            roblox_id = str(roblox)

        restriction = await get_restriction("users", author.id) or await get_restriction("robloxAccounts", roblox_id)

        if restriction:
            raise Blacklisted(restriction)

        user_data = await self.r.db("bloxlink").table("users").get(author_id).run()
        roblox_accounts = user_data.get("robloxAccounts", {})
        roblox_list = roblox_accounts.get("accounts", [])
        guilds = roblox_accounts.get("guilds", {})

        if roblox_id in roblox_list:
            roblox_list.remove(roblox_id)
            roblox_accounts["accounts"] = roblox_list
            success = True

        for i,v in dict(guilds).items():
            if v == roblox_id:
                try:
                    guild = await Bloxlink.fetch_guild(int(i))
                except (discord.errors.Forbidden, discord.errors.HTTPException):
                    pass
                else:
                    try:
                        member = await guild.fetch_member(author.id)
                    except (discord.errors.Forbidden, discord.errors.NotFound):
                        pass
                    else:
                        for role in member.roles:
                            if role != guild.default_role and role.name != "Muted":
                                try:
                                    await member.remove_roles(role, reason="Unlinked")
                                except discord.errors.Forbidden:
                                    pass

                guilds.pop(i, None)

                success = True


        if user_data.get("robloxID") == roblox_id:
            user_data["robloxID"] = None

        roblox_accounts["guilds"] = guilds
        user_data["robloxAccounts"] = roblox_accounts

        roblox_discord_data = await self.r.db("bloxlink").table("robloxAccounts").get(roblox_id).run() or {"id": roblox_id}
        discord_ids = roblox_discord_data.get("discordIDs") or []

        if author_id in discord_ids:
            discord_ids.remove(author_id)

            if not discord_ids:
                await self.r.table("robloxAccounts").get(roblox_id).delete().run()
            else:
                roblox_discord_data["discordIDs"] = discord_ids

                await self.r.table("robloxAccounts").insert(roblox_discord_data, conflict="replace").run()


        await self.r.db("bloxlink").table("users").insert(user_data, conflict="replace").run()

        await cache_pop(f"discord_profiles:{author_id}")

        return success


    async def get_clan_tag(self, author, guild, response, dm=False, user_data=None):
        user_data = user_data or await self.r.db("bloxlink").table("users").get(str(author.id)).run() or {"id": str(author.id)}
        clan_tags = user_data.get("clanTags", {})

        def get_from_db():
            return clan_tags.get(str(guild.id))

        if not response:
            return get_from_db()

        clan_tag = (await response.prompt([{
            "prompt": "Please provide text for your Clan Tag. This will be inserted into "
                      "your nickname.\n**Please keep your clan tag under 10 characters**, "
                      "or it may not properly show.\nIf you want to skip this, then say `skip`.",
            "name": "clan_tag",
            "max": 32
        }], dm=dm))["clan_tag"]

        if clan_tag.lower() == "skip":
            return get_from_db()

        clan_tags[str(guild.id)] = clan_tag
        user_data["clanTags"] = clan_tags
        await self.r.db("bloxlink").table("users").insert(user_data, conflict="update").run()

        return clan_tag

    async def format_update_embed(self, roblox_user, author, added, removed, errors, warnings, *, nickname, prefix, guild_data):
        welcome_message = guild_data.get("welcomeMessage", DEFAULTS.get("welcomeMessage"))
        welcome_message = await self.get_nickname(author, welcome_message, guild_data=guild_data, roblox_user=roblox_user, is_nickname=False, prefix=prefix)

        embed = None

        if added or removed or errors or nickname:
            embed = discord.Embed(title=f":man_office_worker: Role data for {roblox_user.username}")
            embed.set_author(name=str(author), icon_url=author.avatar.url, url=roblox_user.profile_link)
            embed.set_thumbnail(url=roblox_user.avatar)

            if nickname:
                embed.add_field(name="Nickname", value=nickname)
            if added:
                embed.add_field(name="Added Roles", value=", ".join(added))
            if removed:
                embed.add_field(name="Removed Roles", value=", ".join(removed))
            if errors:
                embed.add_field(name="Errors", value=", ".join(errors))
        else:
            embed = discord.Embed(description="This user is all up-to-date; no changes were made.")

        if warnings:
            embed.set_footer(text=" | ".join(warnings))

        view = discord.ui.View()
        view.add_item(item=discord.ui.Button(style=discord.ButtonStyle.link, label="Add/Change Account", url=VERIFY_URL, emoji="🔗"))
        view.add_item(item=discord.ui.Button(style=discord.ButtonStyle.link, label="Remove Account", emoji="🧑‍🔧", url=ACCOUNT_SETTINGS_URL))

        return welcome_message, embed, view

    async def get_nickname(self, author, template=None, group=None, *, guild=None, skip_roblox_check=False, response=None, is_nickname=True, guild_data=None, user_data=None, roblox_user=None, dm=False, prefix=None):
        template = template or ""

        if template == "{disable-nicknaming}":
            return

        guild = guild or author.guild
        roblox_user = roblox_user or (not skip_roblox_check and await self.get_user(author=author, everything=True))

        if isinstance(roblox_user, tuple):
            roblox_user = roblox_user[0]

        guild_data = guild_data or await self.r.table("guilds").get(str(guild.id)).run() or {}

        if roblox_user:
            if not roblox_user.complete:
                await roblox_user.sync(everything=True)

            if not group and guild_data:
                groups = list(guild_data.get("groupIDs", {}).keys())
                group_id = groups and groups[0]

                if group_id:
                    group = roblox_user.groups.get(group_id)

            group_role = group and group.user_rank_name or "Guest"

            if guild_data.get("shorterNicknames", DEFAULTS.get("shorterNicknames")):
                if group_role != "Guest":
                    brackets_match = bracket_search.search(group_role)

                    if brackets_match:
                        group_role = f"[{brackets_match.group(1)}]"

            template = template or DEFAULTS.get("nicknameTemplate") or ""

            if template == "{disable-nicknaming}":
                return

            for group_id in any_group_nickname.findall(template):
                group = roblox_user.groups.get(group_id)
                group_role_from_group = group and group.user_rank_name or "Guest"

                if guild_data.get("shorterNicknames", DEFAULTS.get("shorterNicknames")):
                    if group_role_from_group != "Guest":
                        brackets_match = bracket_search.search(group_role_from_group)

                        if brackets_match:
                            group_role_from_group = f"[{brackets_match.group(1)}]"

                template = template.replace("{group-rank-"+group_id+"}", group_role_from_group)

            if "smart-name" in template:
                if roblox_user.display_name != roblox_user.username:
                    smart_name = f"{roblox_user.display_name} (@{roblox_user.username})"

                    if len(smart_name) > 32:
                        smart_name = roblox_user.username
                else:
                    smart_name = roblox_user.username
            else:
                smart_name = ""

            template = template.replace(
                "roblox-name", roblox_user.username
            ).replace(
                "display-name", roblox_user.display_name,
            ).replace(
                "smart-name", smart_name,
            ).replace(
                "roblox-id", str(roblox_user.id)
            ).replace(
                "roblox-age", str(roblox_user.age)
            ).replace(
                "roblox-join-date", roblox_user.join_date
            ).replace(
                "group-rank", group_role
            )

        else:
            if not template:
                template = guild_data.get("unverifiedNickname") or DEFAULTS.get("unverifiedNickname") or ""

                if template == "{disable-nicknaming}":
                    return

        template = template.replace(
            "discord-name", author.name
        ).replace(
            "discord-nick", author.display_name
        ).replace(
            "discord-mention", author.mention
        ).replace(
            "discord-id", str(author.id)
        ).replace(
            "server-name", guild.name
        ).replace(
            "prefix", prefix or PREFIX
        )

        for outer_nick in nickname_template_regex.findall(template):
            nick_data = outer_nick.split(":")
            nick_fn = None
            nick_value = None

            if len(nick_data) > 1:
                nick_fn = nick_data[0]
                nick_value = nick_data[1]
            else:
                nick_value = nick_data[0]

            # nick_fn = capA
            # nick_value = roblox-name

            if nick_fn:
                if nick_fn in ("allC", "allL"):
                    if nick_fn == "allC":
                        nick_value = nick_value.upper()
                    elif nick_fn == "allL":
                        nick_value = nick_value.lower()

                    template = template.replace("{{{0}}}".format(outer_nick), nick_value)
                else:
                    template = template.replace("{{{0}}}".format(outer_nick), outer_nick) # remove {} only
            else:
                template = template.replace("{{{0}}}".format(outer_nick), nick_value)

        # clan tags are done at the end bc we may need to shorten them, and brackets are removed at the end
        clan_tag = "clan-tag" in template and (await self.get_clan_tag(author=author, guild=guild, response=response, user_data=user_data, dm=dm) or "N/A")

        if is_nickname:
            if clan_tag:
                characters_left = 32 - len(template) + 8
                clan_tag = clan_tag[:characters_left]
                template = template.replace("clan-tag", clan_tag)

            return template[:32]
        else:
            if clan_tag:
                template = template.replace("clan-tag", clan_tag)

            return template


    async def parse_trello_binds(self, trello_board=None, trello_binds_list=None):
        card_binds = {
            "groups": {
                "binds": {},
                "entire group": {}
            },
            "assets": {},
            "badges": {},
            "gamePasses": {}
        }

        if trello_board or trello_binds_list:
            trello_binds_list = trello_binds_list or await trello_board.get_list(lambda l: l.name.lower() == "bloxlink binds")

            if trello_binds_list:
                if hasattr(trello_binds_list, "parsed_bind_data") and trello_binds_list.parsed_bind_data:
                    card_binds = trello_binds_list.parsed_bind_data
                else:
                    await trello_binds_list.sync(card_limit=TRELLO["CARD_LIMIT"])

                    for card in await trello_binds_list.get_cards():
                        is_bind = False
                        is_main_group = False
                        treat_as_bind = False
                        bind_category = None
                        new_bind = {"trello_str": {}, "nickname": None, "removeRoles": set(), "trello": True, "card": card}

                        for card_bind_data in card.description.split("\n"):
                            card_bind_data_search = trello_card_bind_regex.search(card_bind_data)

                            if card_bind_data_search:
                                card_attr, card_value = card_bind_data_search.groups()

                                if card_attr and card_value:
                                    card_attr = card_attr.lower()

                                    if card_attr in ("group", "groupid", "group id"):
                                        if not card_value.isdigit():
                                            raise Error(f"Mess up on Trello bind Group configuration: `{card_value}` is not an integer.")

                                        new_bind["group"] = card_value
                                        new_bind["trello_str"]["group"] = card_value
                                        bind_category = "group"

                                    elif card_attr in ("asset", "assetid", "asset id"):
                                        if not card_value.isdigit():
                                            raise Error(f"Mess up on Trello bind Asset configuration: `{card_value}` is not an integer.")

                                        bind_category = "asset"
                                        new_bind["bind_id"] = card_value

                                    elif card_attr in ("badge", "badgeid", "badge id"):
                                        if not card_value.isdigit():
                                            raise Error(f"Mess up on Trello bind Badge configuration: `{card_value}` is not an integer.")

                                        bind_category = "badge"
                                        new_bind["bind_id"] = card_value

                                    elif card_attr in ("gamepass", "gamepassid", "gamepass id"):
                                        if not card_value.isdigit():
                                            raise Error(f"Mess up on Trello bind GamePass configuration: `{card_value}` is not an integer.")

                                        bind_category = "gamepass"
                                        new_bind["bind_id"] = card_value

                                    elif card_attr == "nickname":
                                        if card_value.lower() not in ("none", "false", "n/a"):
                                            new_bind["nickname"] = card_value
                                        else:
                                            new_bind["nickname"] = None

                                        new_bind["trello_str"]["nickname"] = card_value

                                    elif card_attr == "ranks":
                                        is_bind = True
                                        new_bind["ranks"] = []

                                        for rank in card_value.split(","):
                                            rank = rank.replace(" ", "")

                                            if not rank.isdigit() and rank != "guest" and "-" not in rank:
                                                raise Error(f"Mess up on Trello bind rank configuration: `{rank}` is not an integer.")

                                            new_bind["ranks"].append(rank)

                                        new_bind["trello_str"]["ranks"] = card_value

                                    elif card_attr == "roles":
                                        new_bind["roles"] = set([r.strip() for r in card_value.split(",")])
                                        new_bind["trello_str"]["roles"] = card_value

                                    elif card_attr == "display name":
                                        new_bind["displayName"] = card_value
                                        new_bind["trello_str"]["vg_name"] = card_value

                                    elif card_attr == "remove roles":
                                        new_bind["removeRoles"] = set([r.strip() for r in card_value.split(",")])
                                        new_bind["trello_str"]["remove_roles"] = card_value

                        bind_nickname = new_bind.get("nickname")
                        bound_roles = new_bind.get("roles", set())

                        if bind_category == "group":
                            if new_bind.get("group"):
                                if not (new_bind.get("roles") or is_bind):
                                    is_main_group = True
                                else:
                                    treat_as_bind = True
                            else:
                                continue

                            if treat_as_bind:
                                if new_bind.get("ranks"):
                                    ranges = []

                                    for rank in new_bind["ranks"]:
                                        is_range = False
                                        new_range = None

                                        if rank == "everyone":
                                            rank = "all"
                                        elif "-" in rank and not rank.lstrip("-").isdigit():
                                            range_data = rank.split("-")

                                            if len(range_data) == 2:
                                                if not range_data[0].isdigit() and range_data[0] != "0":
                                                    raise Error(f"Mess up on Trello bind configuration for range: `{range_data[0]}` is not an integer.")
                                                elif not range_data[1].isdigit() and range_data[1] != "0":
                                                    raise Error(f"Mess up on Trello bind configuration for range: `{range_data[1]}` is not an integer.")

                                                is_range = True
                                                new_range = {
                                                    "low": int(range_data[0].strip()),
                                                    "high": int(range_data[1].strip()),
                                                    "nickname": bind_nickname,
                                                    "removeRoles": new_bind.get("removeRoles"),
                                                    "roles": bound_roles,
                                                    "trello": {
                                                        "cards": [{
                                                            "card": card,
                                                            "trello_str": new_bind["trello_str"],
                                                            "ranks": new_bind.get("ranks"),
                                                            "roles": bound_roles
                                                        }]
                                                    }
                                                }
                                                #ranges.append(new_range)

                                        card_binds["groups"]["binds"][new_bind["group"]] = card_binds["groups"]["binds"].get(new_bind["group"]) or {}
                                        card_binds["groups"]["binds"][new_bind["group"]]["binds"] = card_binds["groups"]["binds"][new_bind["group"]].get("binds") or {}
                                        card_binds["groups"]["binds"][new_bind["group"]]["ranges"] = card_binds["groups"]["binds"][new_bind["group"]].get("ranges") or []
                                        card_binds["groups"]["binds"][new_bind["group"]]["ranges"] += ranges

                                        new_rank = {"nickname": bind_nickname, "roles": bound_roles, "removeRoles": new_bind.get("removeRoles"), "trello": {"cards": [{"roles": set(bound_roles), "card": card, "trello_str": new_bind["trello_str"], "ranks": new_bind.get("ranks") }]}}

                                        if not is_range:
                                            old_rank = card_binds["groups"]["binds"][new_bind["group"]]["binds"].get(rank)

                                            if old_rank:
                                                new_rank["roles"].update(old_rank["roles"])
                                                new_rank["removeRoles"].update(old_rank["removeRoles"])
                                                new_rank["trello"]["cards"] += old_rank["trello"]["cards"]

                                            card_binds["groups"]["binds"][new_bind["group"]]["binds"][rank] = new_rank
                                        else:
                                            new_range.update({
                                                "high": new_range["high"],
                                                "low": new_range["low"]
                                            })

                                            for range_ in card_binds["groups"]["binds"][new_bind["group"]]["ranges"]:
                                                if range_["high"] == new_range["high"] and range_["low"] == new_range["low"]:
                                                    old_range = range_

                                                    new_range["roles"].update(old_range["roles"])
                                                    new_range["removeRoles"].update(old_range["removeRoles"])
                                                    new_range["trello"]["cards"] += old_range["trello"]["cards"]

                                                    break

                                            card_binds["groups"]["binds"][new_bind["group"]]["ranges"].append(new_range)

                                else:
                                    new_rank = {
                                        "nickname": bind_nickname,
                                        "roles": bound_roles,
                                        "removeRoles": new_bind.get("removeRoles"),
                                        "trello": {
                                            "cards": [{
                                                "card": card,
                                                "trello_str": new_bind["trello_str"],
                                                "ranks": new_bind.get("ranks"),
                                                "roles": bound_roles
                                            }]
                                        }
                                    }

                                    card_binds["groups"]["binds"][new_bind["group"]] = card_binds["groups"]["binds"].get(new_bind["group"]) or {}
                                    card_binds["groups"]["binds"][new_bind["group"]]["binds"] = card_binds["groups"]["binds"][new_bind["group"]].get("binds") or {}

                                    old_rank = card_binds["groups"]["binds"][new_bind["group"]]["binds"].get("all")

                                    if old_rank:
                                        new_rank["roles"] = new_rank["roles"].union(old_rank["roles"])
                                        new_rank["removeRoles"] = new_rank["removeRoles"].union(old_rank["removeRoles"])
                                        new_rank["trello"]["cards"] += old_rank["trello"]["cards"]

                                    card_binds["groups"]["binds"][new_bind["group"]]["binds"]["all"] = new_rank

                            elif is_main_group:
                                try:
                                    group = await self.get_group(new_bind["group"], full_group=True)
                                except RobloxNotFound:
                                    group_name = f"Invalid Group: {new_bind['group']}"
                                else:
                                    group_name = group.name

                                new_rank = {
                                    "nickname": bind_nickname,
                                    "groupName": group_name,
                                    "removeRoles": new_bind.get("removeRoles"),
                                    "roles": bound_roles, # set(),
                                    "trello": {
                                        "cards": [{
                                            "card": card,
                                            "trello_str": new_bind["trello_str"],
                                            "ranks": new_bind.get("ranks")
                                        }]
                                    }
                                }

                                old_rank = card_binds["groups"]["entire group"].get(new_bind["group"])

                                if old_rank:
                                    new_rank["roles"] = new_rank["roles"].union(old_rank["roles"])
                                    new_rank["removeRoles"] = new_rank["removeRoles"].union(old_rank["removeRoles"])
                                    new_rank["trello"]["cards"] += old_rank["trello"]["cards"]

                                card_binds["groups"]["entire group"][new_bind["group"]] = new_rank

                        elif bind_category in ("asset", "badge", "gamepass"):
                            if bind_category == "gamepass":
                                bind_category_plural = "gamePasses"
                            else:
                                bind_category_plural = f"{bind_category}s"

                            new_rank = {
                                "nickname": bind_nickname,
                                "displayName": new_bind.get("displayName"),
                                "removeRoles": new_bind.get("removeRoles"),
                                "roles": bound_roles,
                                "trello": {
                                    "cards": [{
                                        "card": card,
                                        "trello_str": new_bind["trello_str"],
                                    }]
                                }
                            }
                            old_rank = card_binds[bind_category_plural].get(new_bind["bind_id"])

                            if old_rank:
                                new_rank["roles"] = new_rank["roles"].union(old_rank["roles"])
                                new_rank["removeRoles"] = new_rank["removeRoles"].union(old_rank["removeRoles"])
                                new_rank["trello"]["cards"] += old_rank["trello"]["cards"]

                            card_binds[bind_category_plural][new_bind["bind_id"]] = new_rank


                    trello_binds_list.parsed_bind_data = card_binds

        return card_binds, trello_binds_list


    async def get_binds(self, guild=None, guild_data=None, trello_board=None, trello_binds_list=None, given_trello_options=False):
        guild_data = guild_data or await self.r.table("guilds").get(str(guild.id)).run() or {}
        role_binds = guild_data.get("roleBinds") or {}
        group_ids  = guild_data.get("groupIDs") or {}

        role_binds["groups"]     = role_binds.get("groups", {})
        role_binds["assets"]     = role_binds.get("assets", {})
        role_binds["badges"]     = role_binds.get("badges", {})
        role_binds["gamePasses"] = role_binds.get("gamePasses", {})

        if trello_board:
            card_binds, trello_binds_list = await self.parse_trello_binds(trello_board=trello_board, trello_binds_list=trello_binds_list)
            mode = guild_data.get("trelloBindMode", DEFAULTS.get("trelloBindMode"))

            if not given_trello_options:
                trello_options, _ = await get_options(trello_board)
                mode = trello_options.get("trelloBindMode", mode)

            group_binds    = card_binds["groups"].get("binds")
            asset_binds    = card_binds["assets"]
            badge_binds    = card_binds["badges"]
            gamepass_binds = card_binds["gamePasses"]
            entire_group   = card_binds["groups"]["entire group"]

            if mode == "replace":
                role_binds = {
                    "groups": group_binds,
                    "assets": asset_binds,
                    "badges": badge_binds,
                    "gamePasses": gamepass_binds
                }
                group_ids = entire_group

            else:
                for category, bind_data in card_binds.items():
                    role_binds[category] = role_binds.get(category, {})

                    if category == "groups":
                        role_binds["groups"].update(group_binds)
                    else:

                        role_binds[category].update(bind_data)

                group_ids.update(entire_group)


        return role_binds, group_ids, trello_binds_list


    async def guild_obligations(self, member, guild, join=None, guild_data=None, cache=True, dm=False, event=False, response=None, exceptions=False, roles=True, nickname=True, trello_board=None, roblox_user=None):
        if member.bot:
            raise CancelCommand

        if self.pending_verifications.get(member.id):
            raise CancelCommand("You are already queued for verification. This process can take a while depending on the size of the server due to Discord rate-limits.")

        self.pending_verifications[member.id] = True

        try:
            roblox_user = None
            accounts = []
            donator_profile = None
            unverified = False
            exceptions = exceptions or ()
            added, removed, errored, warnings, chosen_nickname = [], [], [], [], None

            if RELEASE == "PRO":
                donator_profile, _ = await get_features(discord.Object(id=guild.owner_id), guild=guild)

                if not donator_profile.features.get("pro"):
                    raise CancelCommand

                PREFIX = "!"
            else:
                PREFIX = "!!"

            try:
                roblox_user, accounts = await self.get_user(author=member, everything=True, cache=cache)
            except UserNotVerified:
                unverified = True
            except RobloxAPIError as e:
                if "RobloxAPIError" in exceptions:
                    raise RobloxAPIError from e
            except RobloxDown:
                if "RobloxDown" in exceptions:
                    raise RobloxDown
                else:
                    raise CancelCommand

            if not roblox_user:
                unverified = True

            async def post_log(channel_data, color):
                if event and channel_data:
                    if not unverified:
                        if channel_data.get("verified"):
                            channel_id = int(channel_data["verified"]["channel"])
                            channel = discord.utils.find(lambda c: c.id == channel_id, guild.text_channels)

                            if channel:
                                join_channel_message = channel_data["verified"]["message"]
                                join_message_parsed = (await self.get_nickname(member, join_channel_message, guild_data=guild_data, roblox_user=roblox_user, dm=dm, is_nickname=False))[:1500]
                                includes = channel_data["verified"]["includes"]

                                embed   = discord.Embed(description=join_message_parsed)
                                content = None
                                view    = None
                                use_embed = False

                                if includes:
                                    embed_description_buffer = []

                                    if includes.get("robloxAvatar"):
                                        use_embed = True
                                        embed.set_thumbnail(url=roblox_user.avatar)

                                    if includes.get("robloxUsername"):
                                        use_embed = True
                                        embed_description_buffer.append(f"**Roblox username:** {roblox_user.username}")

                                    if includes.get("robloxAge"):
                                        use_embed = True
                                        embed_description_buffer.append(f"**Roblox account age:** {roblox_user.full_join_string}")

                                    if use_embed:
                                        embed.set_author(name=str(member), icon_url=member.avatar.url, url=roblox_user.profile_link)
                                        embed.set_footer(text="Disclaimer: the message above was set by the Server Admins. The ONLY way to verify with Bloxlink "
                                                            "is through https://blox.link and NO other link.")
                                        embed.colour = color

                                        view = discord.ui.View()
                                        view.add_item(item=discord.ui.Button(style=discord.ButtonStyle.link, label="Visit Profile", url=roblox_user.profile_link, emoji="👥"))

                                        if embed_description_buffer:
                                            embed_description_buffer = "\n".join(embed_description_buffer)
                                            embed.description = f"{embed.description}\n\n{embed_description_buffer}"

                                if not use_embed:
                                    embed = None
                                    content = f"{join_message_parsed}\n\n**Disclaimer:** the message above was set by the Server Admins. The ONLY way to verify with Bloxlink " \
                                            "is through <https://blox.link> and NO other link."

                                if includes.get("ping"):
                                    content = f"{member.mention} {content or ''}"

                                try:
                                    await channel.send(content=content, embed=embed, view=view)
                                except (discord.errors.NotFound, discord.errors.Forbidden):
                                    pass
                    else:
                        if channel_data.get("unverified"):
                            channel_id = int(channel_data["unverified"]["channel"])
                            channel = discord.utils.find(lambda c: c.id == channel_id, guild.text_channels)

                            if channel:
                                join_channel_message = channel_data["unverified"]["message"]
                                join_message_parsed = (await self.get_nickname(member, join_channel_message, guild_data=guild_data, skip_roblox_check=True, dm=dm, is_nickname=False))[:2000]
                                includes = channel_data["unverified"]["includes"]
                                format_embed = channel_data["unverified"]["embed"]

                                embed   = None
                                content = None

                                if format_embed:
                                    embed = discord.Embed(description=join_message_parsed)
                                    embed.set_author(name=str(member), icon_url=member.avatar.url)
                                    embed.set_footer(text="Disclaimer: the message above was set by the Server Admins. The ONLY way to verify with Bloxlink "
                                                        "is through https://blox.link and NO other link.")
                                    embed.colour = color
                                else:
                                    content = f"{join_message_parsed}\n\n**Disclaimer:** the message above was set by the Server Admins. The ONLY way to verify with Bloxlink " \
                                            "is through <https://blox.link> and NO other link."

                                if includes.get("ping"):
                                    content = f"{member.mention} {content or ''}"

                                try:
                                    await channel.send(content=content, embed=embed)
                                except (discord.errors.NotFound, discord.errors.Forbidden):
                                    pass

            if join is not False:
                options, guild_data = await get_guild_value(guild, ["verifiedDM", DEFAULTS.get("welcomeMessage")], ["unverifiedDM", DEFAULTS.get("unverifiedDM")], "ageLimit", ["disallowAlts", DEFAULTS.get("disallowAlts")], ["disallowBanEvaders", DEFAULTS.get("disallowBanEvaders")], "groupLock", "joinChannel", return_guild_data=True)

                verified_dm = options.get("verifiedDM")
                join_channel = options.get("joinChannel")
                unverified_dm = options.get("unverifiedDM")
                age_limit = options.get("ageLimit")
                disallow_alts = options.get("disallowAlts")
                disallow_ban_evaders = options.get("disallowBanEvaders")

                try:
                    age_limit = int(age_limit) #FIXME
                except TypeError:
                    age_limit = None

                if disallow_alts or disallow_ban_evaders:
                    if not donator_profile:
                        donator_profile, _ = await get_features(discord.Object(id=guild.owner_id), guild=guild)

                    if donator_profile.features.get("premium"):
                        accounts = set(accounts)

                        if roblox_user: #FIXME: temp until primary accounts are saved to the accounts array
                            accounts.add(roblox_user.id)

                        if accounts and (disallow_alts or disallow_ban_evaders):
                            for roblox_id in accounts:
                                discord_ids = (await self.r.db("bloxlink").table("robloxAccounts").get(roblox_id).run() or {}).get("discordIDs") or []

                                for discord_id in discord_ids:
                                    discord_id = int(discord_id)

                                    if discord_id != member.id:
                                        if disallow_alts:
                                            # check the server

                                            try:
                                                user_find = await guild.fetch_member(discord_id)
                                            except discord.errors.NotFound:
                                                pass
                                            else:
                                                try:
                                                    await user_find.kick(reason=f"disallowAlts is enabled - alt of {member} ({member.id})")
                                                except discord.errors.Forbidden:
                                                    pass
                                                else:
                                                    await post_event(guild, guild_data, "moderation", f"{user_find.mention} is an alt of {member.mention} and has been `kicked`.", RED_COLOR)

                                                    raise CancelCommand

                                        if disallow_ban_evaders:
                                            # check the bans

                                            try:
                                                ban_entry = await guild.fetch_ban(discord.Object(discord_id))
                                            except (discord.errors.NotFound, discord.errors.Forbidden):
                                                pass
                                            else:
                                                action = disallow_ban_evaders == "kick" and "kick"   or "ban"
                                                action_participle    = action == "kick" and "kicked" or "banned"

                                                try:
                                                    await ((getattr(guild, action))(member, reason=f"disallowBanEvaders is enabled - alt of {ban_entry.user} ({ban_entry.user.id})"))
                                                except (discord.errors.Forbidden, discord.errors.HTTPException):
                                                    pass
                                                else:
                                                    await post_event(guild, guild_data, "moderation", f"{member.mention} is an alt of {ban_entry.user.mention} and has been `{action_participle}`.", RED_COLOR)

                                                    raise CancelCommand

                                                return added, removed, chosen_nickname, errored, warnings, roblox_user
                try:
                    added, removed, chosen_nickname, errored, warnings, _ = await self.update_member(
                        member,
                        guild                   = guild,
                        guild_data              = guild_data,
                        roles                   = roles,
                        trello_board            = trello_board,
                        nickname                = nickname,
                        roblox_user             = roblox_user,
                        given_trello_options    = True,
                        cache                   = cache,
                        dm                      = dm,
                        response                = response)

                except discord.errors.NotFound as e:
                    if "NotFound" in exceptions:
                        raise e from None
                except RobloxAPIError as e:
                    if "RobloxAPIError" in exceptions:
                        raise e from None
                except Error as e:
                    if "Error" in exceptions:
                        raise e from None
                except CancelCommand as e:
                    if "CancelCommand" in exceptions:
                        raise e from None
                except RobloxDown as e:
                    if "RobloxDown" in exceptions:
                        raise e from None
                    else:
                        raise CancelCommand
                except Blacklisted as e:
                    if "Blacklisted" in exceptions:
                        raise e from None
                except BloxlinkBypass as e:
                    if "BloxlinkBypass" in exceptions:
                        raise e from None
                except PermissionError as e:
                    if "PermissionError" in exceptions:
                        raise e from None

                except (UserNotVerified, discord.errors.HTTPException):
                    pass

                required_groups = options.get("groupLock") # TODO: integrate with Trello

                if roblox_user:
                    if event:
                        await post_event(guild, guild_data, "verification", f"{member.mention} has **verified** as `{roblox_user.username}`.", GREEN_COLOR)

                    if age_limit:
                        if age_limit > roblox_user.age:
                            if dm:
                                try:
                                    await member.send(f"_Bloxlink Age-Limit_\nYou were kicked from **{guild.name}** for not being at least "
                                                    f"`{age_limit}` days old on your Roblox account `{roblox_user.username}` (days={roblox_user.age}). If this is a mistake, "
                                                    f"then please join {SERVER_INVITE} and link a different account with `{PREFIX}verify add`. "
                                                    f"Finally, use the `{PREFIX}switchuser` command and provide this ID to the command: `{guild.id}`")
                                except discord.errors.Forbidden:
                                    pass

                            try:
                                await member.kick(reason=f"AGE-LIMIT: user age {roblox_user.age} < {age_limit}")
                            except discord.errors.Forbidden:
                                pass
                            else:
                                raise CancelCommand

                            return added, removed, chosen_nickname, errored, warnings, roblox_user

                    if required_groups:
                        for group_id, group_data in required_groups.items():
                            group = roblox_user.groups.get(group_id)

                            if group:
                                if group_data.get("roleSets"):
                                    for allowed_roleset in group_data["roleSets"]:
                                        if isinstance(allowed_roleset, list):
                                            if allowed_roleset[0] <= group.user_rank_id <= allowed_roleset[1]:
                                                break
                                        else:
                                            if (group.user_rank_id == allowed_roleset) or (allowed_roleset < 0 and abs(allowed_roleset) <= group.user_rank_id):
                                                break
                                    else:
                                        if dm:
                                            dm_message = group_data.get("dmMessage")
                                            group_url = f"https://www.roblox.com/groups/{group_id}/-"

                                            if dm_message:
                                                text = (f"_Bloxlink Server-Lock_\nYour Roblox account `{roblox_user.username}` is not in the group "
                                                        f"{group_url}, so you cannot join the **{guild.name}** server.\n\nWrong account? Go to <https://blox.link/verification/{guild.id}> and change it!\n\n"
                                                        f"Need additional help? Go to {SERVER_INVITE} and ask for help!\n\n"
                                                        f"These instructions were set by the Server Admins:\n\n{dm_message}")
                                            else:
                                                text = (f"_Bloxlink Server-Lock_\nYour Roblox account `{roblox_user.username}` doesn't have an allowed Roleset in the group "
                                                        f"{group_url}, so you cannot join the **{guild.name}** server.\n\nWrong account? Go to <https://blox.link/verification/{guild.id}> and change it!\n\n"
                                                        f"Need additional help? Go to {SERVER_INVITE} and ask for help!")
                                            try:
                                                await member.send(text)
                                            except discord.errors.Forbidden:
                                                pass
                                        try:
                                            await member.kick(reason=f"SERVER-LOCK: doesn't have the allowed roleset(s) for group {group_id}")
                                        except discord.errors.Forbidden:
                                            pass
                                        else:
                                            raise CancelCommand

                                        return added, removed, chosen_nickname, errored, warnings, roblox_user
                            else:
                                if dm:
                                    dm_message = group_data.get("dmMessage")
                                    group_url = f"https://www.roblox.com/groups/{group_id}/-"

                                    if dm_message:
                                        text = (f"_Bloxlink Server-Lock_\nYour Roblox account `{roblox_user.username}` is not in the group "
                                                f"{group_url}, so you cannot join the **{guild.name}** server.\n\nWrong account? Go to <https://blox.link/verification/{guild.id}> and change it!\n\n"
                                                f"Need additional help? Go to {SERVER_INVITE} and ask for help!\n\nThese instructions were set by the Server Admins:\n\n{dm_message}`")
                                    else:
                                        text = (f"_Bloxlink Server-Lock_\nYour Roblox account `{roblox_user.username}` is not in the group "
                                                f"{group_url}, so you cannot join the **{guild.name}** server.\n\nWrong account? Go to <https://blox.link/verification/{guild.id}> and change it!\n\n"
                                                f"Need additional help? Go to {SERVER_INVITE} and ask for help!")

                                    try:
                                        await member.send(text)
                                    except discord.errors.Forbidden:
                                        pass
                                try:
                                    await member.kick(reason=f"SERVER-LOCK: not in group {group_id}")
                                except discord.errors.Forbidden:
                                    pass
                                else:
                                    raise CancelCommand

                                return added, removed, chosen_nickname, errored, warnings, roblox_user

                    if dm and verified_dm:
                        if verified_dm != DEFAULTS.get("welcomeMessage"):
                            verified_dm = f"This message was set by the Server Admins:\n{verified_dm}"

                        verified_dm = (await self.get_nickname(member, verified_dm, guild_data=guild_data, roblox_user=roblox_user, dm=dm, is_nickname=False))[:2000]

                        try:
                            await member.send(verified_dm)
                        except (discord.errors.Forbidden, discord.errors.HTTPException):
                            pass

                    if join is not None:
                        await post_log(join_channel, GREEN_COLOR)

                else:
                    if age_limit:
                        if not donator_profile:
                            donator_profile, _ = await get_features(discord.Object(id=guild.owner_id), guild=guild)

                        if donator_profile.features.get("premium"):
                            if dm:
                                try:
                                    if accounts:
                                        await member.send(f"_Bloxlink Server-Lock_\nYou have no primary account set! Please go to {ACCOUNT_SETTINGS_URL} and set a "
                                                        "primary account, then try rejoining this server.")
                                    else:
                                        await member.send(f"_Bloxlink Server-Lock_\nYou were kicked from **{guild.name}** for not being linked to Bloxlink.\n"
                                                        f"You may link your account to Bloxlink by visiting <https://blox.link/verification/{guild.id}> and completing the verification process.\n"
                                                        "Stuck? Watch this video: <https://youtu.be/0SH3n8rY9Fg>\n"
                                                        f"Join {SERVER_INVITE} for additional help.")
                                except discord.errors.Forbidden:
                                    pass

                            try:
                                await member.kick(reason=f"AGE-LIMIT: user not linked to Bloxlink")
                            except discord.errors.Forbidden:
                                pass
                            else:
                                raise CancelCommand

                            return added, removed, chosen_nickname, errored, warnings, roblox_user

                    if required_groups:
                        if dm:
                            try:
                                if accounts:
                                    await member.send(f"_Bloxlink Server-Lock_\nYou have no primary account set! Please go to {ACCOUNT_SETTINGS_URL} and set a "
                                                    "primary account, then try rejoining this server.")
                                else:
                                    await member.send(f"_Bloxlink Server-Lock_\nYou were kicked from **{guild.name}** for not being linked to Bloxlink.\n"
                                                    f"You may link your account to Bloxlink by visiting <https://blox.link/verification/{guild.id}> and completing the verification process.\n"
                                                    "Stuck? Watch this video: <https://youtu.be/0SH3n8rY9Fg>\n"
                                                    f"Join {SERVER_INVITE} for additional help.")
                            except discord.errors.Forbidden:
                                pass

                        try:
                            await member.kick(reason="SERVER-LOCK: not linked to Bloxlink")
                        except discord.errors.Forbidden:
                            pass
                        else:
                            raise CancelCommand

                        return added, removed, chosen_nickname, errored, warnings, roblox_user

                    if dm and unverified_dm:
                        unverified_dm = await self.get_nickname(member, unverified_dm, guild_data=guild_data, skip_roblox_check=True, dm=dm, is_nickname=False)

                        try:
                            await member.send(unverified_dm)
                        except (discord.errors.Forbidden, discord.errors.HTTPException):
                            pass

                    await post_log(join_channel, GREEN_COLOR)

                if not unverified:
                    return added, removed, chosen_nickname, errored, warnings, roblox_user
                else:
                    if "UserNotVerified" in exceptions:
                        raise UserNotVerified

            elif join == False:
                leave_channel = await get_guild_value(guild, "leaveChannel")

                await post_log(leave_channel, RED_COLOR)
        finally:
            self.pending_verifications.pop(member.id, None)


    async def update_member(self, author, guild, *, nickname=True, roles=True, group_roles=True, roblox_user=None, author_data=None, binds=None, guild_data=None, trello_board=None, given_trello_options=False, response=None, dm=False, cache=True):
        restriction = await get_restriction("users", author.id, guild=guild)

        if restriction:
            raise Blacklisted(restriction)

        if not cache:
            await cache_pop(f"discord_profiles:{author.id}")

        me = getattr(guild, "me", None)
        my_permissions = me and me.guild_permissions

        if my_permissions:
            if roles and not my_permissions.manage_roles:
                raise PermissionError("Sorry, I do not have the proper permissions. "
                                      "Please ensure I have the `Manage Roles` permission.")

            if nickname and not my_permissions.manage_nicknames:
                raise PermissionError("Sorry, I do not have the proper permissions. "
                                      "Please ensure I have the `Manage Nicknames` permission.")

        add_roles, remove_roles = set(), set()
        possible_nicknames = []
        errors = []
        warnings = []
        unverified = False
        top_role_nickname = None
        trello_options = {}

        if not isinstance(author, discord.Member):
            author = await guild.fetch_member(author.id)

            if not author:
                raise CancelCommand

        if not guild:
            guild = getattr(author, "guild", None)

            if not guild:
                raise Error("Unable to resolve a guild from author.")

        guild_data = guild_data or await self.r.table("guilds").get(str(guild.id)).run() or {}

        if has_magic_role(author, guild_data.get("magicRoles"), "Bloxlink Bypass"):
            raise BloxlinkBypass()

        if not trello_board:
            trello_board = await get_board(guild=guild, guild_data=guild_data)

        if trello_board and not given_trello_options:
            trello_options, _ = await get_options(trello_board)
            guild_data.update(trello_options)

        async def give_bind_stuff(binds):
            bind_nickname = binds.get("nickname")
            bound_roles = binds.get("roles")
            bind_remove_roles = binds.get("removeRoles") or []

            for role_id in bound_roles:
                int_role_id = role_id.isdigit() and int(role_id)
                role = discord.utils.find(lambda r: ((int_role_id and r.id == int_role_id) or r.name == role_id) and not r.managed, guild.roles)

                if role:
                    add_roles.add(role)

                    if nickname and bind_nickname and bind_nickname != "skip":
                        if author.top_role == role:
                            top_role_nickname = await self.get_nickname(author=author, template=bind_nickname, roblox_user=roblox_user, user_data=author_data, dm=dm, response=response)

                        resolved_nickname = await self.get_nickname(author=author, template=bind_nickname, roblox_user=roblox_user, user_data=author_data, dm=dm, response=response)

                        if resolved_nickname and not resolved_nickname in possible_nicknames:
                            possible_nicknames.append([role, resolved_nickname])

            for role_id in bind_remove_roles:
                int_role_id = role_id.isdigit() and int(role_id)
                role = discord.utils.find(lambda r: ((int_role_id and r.id == int_role_id) or r.name == role_id) and not r.managed, author.roles)

                if role:
                    remove_roles.add(role)

        async def remove_bind_stuff(binds):
            bound_roles = binds.get("roles")

            for role_id in bound_roles:
                int_role_id = role_id.isdigit() and int(role_id)
                role = discord.utils.find(lambda r: ((int_role_id and r.id == int_role_id) or r.name == role_id) and not r.managed, author.roles)

                if role and not allow_old_roles:
                    remove_roles.add(role)


        verify_role = guild_data.get("verifiedRoleEnabled", DEFAULTS.get("verifiedRoleEnabled"))
        unverify_role = guild_data.get("unverifiedRoleEnabled", DEFAULTS.get("unverifiedRoleEnabled"))

        unverified_role_name = guild_data.get("unverifiedRoleName", DEFAULTS.get("unverifiedRoleName"))
        verified_role_name = guild_data.get("verifiedRoleName", DEFAULTS.get("verifiedRoleName"))

        allow_old_roles = guild_data.get("allowOldRoles", DEFAULTS.get("allowOldRoles"))

        if unverify_role:
            unverified_role = discord.utils.find(lambda r: r.name == unverified_role_name and not r.managed, guild.roles)

        if verify_role:
            verified_role = discord.utils.find(lambda r: r.name == verified_role_name and not r.managed, guild.roles)

        inactive_role = await RobloxProfile.get_inactive_role(guild, guild_data, trello_board)

        try:
            if not roblox_user:
                roblox_user, _ = await self.get_user(author=author, guild=guild, author_data=author_data, everything=True, cache=cache)

                if not roblox_user:
                    raise UserNotVerified

        except UserNotVerified:
            if roles:
                if unverify_role:
                    if not unverified_role:
                        try:
                            unverified_role = await guild.create_role(name=unverified_role_name)
                        except discord.errors.Forbidden:
                            raise PermissionError("I was unable to create the Unverified Role. Please "
                                                  "ensure I have the `Manage Roles` permission.")
                        except discord.errors.HTTPException:
                            raise Error("Unable to create role: this server has reached the max amount of roles!")

                    add_roles.add(unverified_role)

                if verify_role and verified_role and verified_role in author.roles:
                    remove_roles.add(verified_role)

                if inactive_role and inactive_role in author.roles:
                    remove_roles.add(inactive_role)

            if nickname:
                nickname = await self.get_nickname(author=author, skip_roblox_check=True, guild=guild, guild_data=guild_data, dm=dm, user_data=author_data, response=response)

            unverified = True

        else:
            restriction = await get_restriction("robloxAccounts", roblox_user.id, guild=guild, roblox_user=roblox_user)

            if restriction:
                raise Blacklisted(restriction)

            if roles:
                if unverify_role:
                    if unverified_role and unverified_role in author.roles:
                        remove_roles.add(unverified_role)

                if verify_role:
                    verified_role = discord.utils.find(lambda r: r.name == verified_role_name and not r.managed, guild.roles)

                    if not verified_role:
                        try:
                            verified_role = await guild.create_role(
                                name   = verified_role_name,
                                reason = "Creating missing Verified role"
                            )
                        except discord.errors.Forbidden:
                            raise PermissionError("Sorry, I wasn't able to create the Verified role. "
                                                  "Please ensure I have the `Manage Roles` permission.")
                        except discord.errors.HTTPException:
                            raise Error("Unable to create role: this server has reached the max amount of roles!")


                    add_roles.add(verified_role)

                if inactive_role:
                    inactive = await RobloxProfile.is_inactive(author, inactive_role)

                    if inactive:
                        if inactive_role not in author.roles:
                            add_roles.add(inactive_role)
                    else:
                        if inactive_role in author.roles:
                            remove_roles.add(inactive_role)

        if not unverified:
            if group_roles and roblox_user:
                if binds and len(binds) == 2 and binds[0] is not None and binds[1] is not None:
                    role_binds, group_ids = binds
                else:
                    role_binds, group_ids, _ = await self.get_binds(guild_data=guild_data, guild=guild, trello_board=trello_board, given_trello_options=True)

                if role_binds:
                    if isinstance(role_binds, list):
                        role_binds = role_binds[0]

                    for category, all_binds in role_binds.items():
                        if category in ("assets", "badges", "gamePasses"):
                            if category == "gamePasses":
                                category_title = "GamePass"
                            else:
                                category_title = (category[:-1]).title()

                            for bind_id, bind_data in all_binds.items():
                                bind_nickname = bind_data.get("nickname")
                                bound_roles = bind_data.get("roles")
                                bind_remove_roles = bind_data.get("removeRoles") or []

                                json_data, response_ = await fetch(f"https://inventory.roblox.com/v1/users/{roblox_user.id}/items/{category_title}/{bind_id}", json=True, raise_on_failure=False)

                                if isinstance(json_data, dict):
                                    if response_.status != 200:
                                        vg_errors = json_data.get("errors", [])

                                        if vg_errors:
                                            error_message = vg_errors[0].get("message")

                                            if error_message != "The specified user does not exist!": # sent if someone is banned from Roblox
                                                raise Error(f"Bind error for {category_title} ID {bind_id}: `{error_message}`")
                                        else:
                                            raise Error(f"Bind error for {category_title} ID {bind_id}")

                                    if json_data.get("data"):
                                        # TODO: cache this

                                        for role_id in bound_roles:
                                            int_role_id = role_id.isdigit() and int(role_id)
                                            role = discord.utils.find(lambda r: ((int_role_id and r.id == int_role_id) or r.name == role_id) and not r.managed, guild.roles)

                                            if not role:
                                                if bind_data.get("trello"):
                                                    try:
                                                        role = await guild.create_role(name=role_id)
                                                    except discord.errors.Forbidden:
                                                        raise PermissionError(f"Sorry, I wasn't able to create the role {role_id}."
                                                                            "Please ensure I have the `Manage Roles` permission.")
                                                    except discord.errors.HTTPException:
                                                        raise Error("Unable to create role: this server has reached the max amount of roles!")

                                                    else:
                                                        add_roles.add(role)

                                            else:
                                                add_roles.add(role)

                                            if role and nickname and bind_nickname and bind_nickname != "skip":
                                                if author.top_role == role:
                                                    top_role_nickname = await self.get_nickname(author=author, template=bind_nickname, roblox_user=roblox_user, user_data=author_data, dm=dm, response=response)

                                                resolved_nickname = await self.get_nickname(author=author, template=bind_nickname, roblox_user=roblox_user, user_data=author_data, dm=dm, response=response)

                                                if resolved_nickname and not resolved_nickname in possible_nicknames:
                                                    possible_nicknames.append([role, resolved_nickname])

                                        for role_id in bind_remove_roles:
                                            int_role_id = role_id.isdigit() and int(role_id)
                                            role = discord.utils.find(lambda r: ((int_role_id and r.id == int_role_id) or r.name == role_id) and not r.managed, author.roles)

                                            if role:
                                                remove_roles.add(role)
                                    else:
                                        for role_id in bound_roles:
                                            int_role_id = role_id.isdigit() and int(role_id)
                                            role = discord.utils.find(lambda r: ((int_role_id and r.id == int_role_id) or r.name == role_id) and not r.managed, guild.roles)

                                            if not allow_old_roles and role and role in author.roles:
                                                remove_roles.add(role)

                        elif category == "robloxStaff":
                            devforum_data = roblox_user.dev_forum

                            if devforum_data and devforum_data.get("trust_level") == 4:
                                await give_bind_stuff(all_binds)
                            else:
                                await remove_bind_stuff(all_binds)

                        elif category == "devForum":
                            devforum_data = roblox_user.dev_forum

                            if devforum_data and devforum_data.get("trust_level"):
                                await give_bind_stuff(all_binds)
                            else:
                                await remove_bind_stuff(all_binds)

                        elif category == "groups":
                            for group_id, data in all_binds.items():
                                group = roblox_user.groups.get(group_id)

                                for bind_id, bind_data in data.get("binds", {}).items():
                                    rank = None
                                    bind_nickname = bind_data.get("nickname")
                                    bound_roles = bind_data.get("roles")
                                    bind_remove_roles = bind_data.get("removeRoles") or []

                                    try:
                                        rank = int(bind_id)
                                    except ValueError:
                                        pass

                                    if group:
                                        user_rank = group.user_rank_id

                                        if bind_id == "0":
                                            if bound_roles:
                                                for role_id in bound_roles:
                                                    int_role_id = role_id.isdigit() and int(role_id)
                                                    role = discord.utils.find(lambda r: ((int_role_id and r.id == int_role_id) or r.name == role_id) and not r.managed, author.roles)

                                                    if role and not allow_old_roles:
                                                        remove_roles.add(role)

                                        elif (bind_id == "all" or rank == user_rank) or (rank and (rank < 0 and user_rank >= abs(rank))):
                                            if not bound_roles:
                                                bound_roles = {group.user_rank_name}

                                            for role_id in bound_roles:
                                                int_role_id = role_id.isdigit() and int(role_id)
                                                role = discord.utils.find(lambda r: ((int_role_id and r.id == int_role_id) or r.name == role_id) and not r.managed, guild.roles)

                                                if not role:
                                                    if bind_data.get("trello"):
                                                        try:
                                                            role = await guild.create_role(name=role_id)
                                                        except discord.errors.Forbidden:
                                                            raise PermissionError(f"Sorry, I wasn't able to create the role {role_id}."
                                                                                   "Please ensure I have the `Manage Roles` permission.")
                                                        except discord.errors.HTTPException:
                                                            raise Error("Unable to create role: this server has reached the max amount of roles!")

                                                        else:
                                                            add_roles.add(role)
                                                else:
                                                    add_roles.add(role)

                                                if role and nickname and bind_nickname and bind_nickname != "skip":
                                                    if author.top_role == role:
                                                        top_role_nickname = await self.get_nickname(author=author, group=group, template=bind_nickname, roblox_user=roblox_user, user_data=author_data, dm=dm, response=response)

                                                    resolved_nickname = await self.get_nickname(author=author, group=group, template=bind_nickname, roblox_user=roblox_user, user_data=author_data, dm=dm, response=response)

                                                    if resolved_nickname and not resolved_nickname in possible_nicknames:
                                                        possible_nicknames.append([role, resolved_nickname])

                                            for role_id in bind_remove_roles:
                                                int_role_id = role_id.isdigit() and int(role_id)
                                                role = discord.utils.find(lambda r: ((int_role_id and r.id == int_role_id) or r.name == role_id) and not r.managed, author.roles)

                                                if role:
                                                    remove_roles.add(role)

                                        else:
                                            for role_id in bound_roles:
                                                int_role_id = role_id.isdigit() and int(role_id)
                                                role = discord.utils.find(lambda r: ((int_role_id and r.id == int_role_id) or r.name == role_id) and not r.managed, guild.roles)

                                                if not allow_old_roles and role and role in author.roles:
                                                    remove_roles.add(role)
                                    else:
                                        if bind_id == "0":
                                            if bound_roles:
                                                for role_id in bound_roles:
                                                    int_role_id = role_id.isdigit() and int(role_id)
                                                    role = discord.utils.find(lambda r: ((int_role_id and r.id == int_role_id) or r.name == role_id) and not r.managed, guild.roles)

                                                    if not role:
                                                        if bind_data.get("trello"):
                                                            try:
                                                                role = await guild.create_role(name=role_id)
                                                            except discord.errors.Forbidden:
                                                                raise PermissionError(f"Sorry, I wasn't able to create the role {role_id}."
                                                                                       "Please ensure I have the `Manage Roles` permission.")

                                                            except discord.errors.HTTPException:
                                                                raise Error("Unable to create role: this server has reached the max amount of roles!")

                                                            else:
                                                                add_roles.add(role)
                                                    else:
                                                        add_roles.add(role)

                                                    if role and nickname and bind_nickname and bind_nickname != "skip":
                                                        if author.top_role == role:
                                                            top_role_nickname = await self.get_nickname(author=author, group=group, template=bind_nickname, roblox_user=roblox_user, user_data=author_data, dm=dm, response=response)

                                                        resolved_nickname = await self.get_nickname(author=author, group=group, template=bind_nickname, roblox_user=roblox_user, user_data=author_data, dm=dm, response=response)

                                                        if resolved_nickname and not resolved_nickname in possible_nicknames:
                                                            possible_nicknames.append([role, resolved_nickname])

                                            for role_id in bind_remove_roles:
                                                int_role_id = role_id.isdigit() and int(role_id)
                                                role = discord.utils.find(lambda r: ((int_role_id and r.id == int_role_id) or r.name == role_id) and not r.managed, author.roles)

                                                if role:
                                                    remove_roles.add(role)
                                        else:
                                            for role_id in bound_roles:
                                                int_role_id = role_id.isdigit() and int(role_id)
                                                role = discord.utils.find(lambda r: ((int_role_id and r.id == int_role_id) or r.name == role_id) and not r.managed, guild.roles)

                                                if not allow_old_roles and role and role in author.roles:
                                                    remove_roles.add(role)

                                for bind_range in data.get("ranges", []):
                                    bind_nickname = bind_range.get("nickname")
                                    bound_roles = bind_range.get("roles", set())
                                    bind_remove_roles = bind_range.get("removeRoles") or []

                                    if group:
                                        user_rank = group.user_rank_id

                                        if bind_range["low"] <= user_rank <= bind_range["high"]:
                                            if not bound_roles:
                                                bound_roles = {group.user_rank_name}

                                            for role_id in bound_roles:
                                                int_role_id = role_id.isdigit() and int(role_id)
                                                role = discord.utils.find(lambda r: ((int_role_id and r.id == int_role_id) or r.name == role_id) and not r.managed, guild.roles)

                                                if not role:
                                                    if bind_range.get("trello"):
                                                        try:
                                                            role = await guild.create_role(name=role_id)
                                                        except discord.errors.Forbidden:
                                                            raise PermissionError(f"Sorry, I wasn't able to create the role {role_id}."
                                                                                    "Please ensure I have the `Manage Roles` permission.")
                                                        except discord.errors.HTTPException:
                                                            raise Error("Unable to create role: this server has reached the max amount of roles!")
                                                if role:
                                                    if roles:
                                                        add_roles.add(role)

                                                        if nickname and author.top_role == role and bind_nickname:
                                                            top_role_nickname = await self.get_nickname(author=author, group=group, template=bind_nickname, roblox_user=roblox_user, user_data=author_data, dm=dm, response=response)

                                                    if nickname and bind_nickname and bind_nickname != "skip":
                                                        resolved_nickname = await self.get_nickname(author=author, group=group, template=bind_nickname, roblox_user=roblox_user, user_data=author_data, dm=dm, response=response)

                                                        if resolved_nickname and not resolved_nickname in possible_nicknames:
                                                            possible_nicknames.append([role, resolved_nickname])

                                            for role_id in bind_remove_roles:
                                                int_role_id = role_id.isdigit() and int(role_id)
                                                role = discord.utils.find(lambda r: ((int_role_id and r.id == int_role_id) or r.name == role_id) and not r.managed, author.roles)

                                                if role:
                                                    remove_roles.add(role)
                                        else:
                                            for role_id in bound_roles:
                                                int_role_id = role_id.isdigit() and int(role_id)
                                                role = discord.utils.find(lambda r: ((int_role_id and r.id == int_role_id) or r.name == role_id) and not r.managed, guild.roles)

                                                if not allow_old_roles and role and role in author.roles:
                                                    remove_roles.add(role)
                                    else:
                                        for role_id in bound_roles:
                                            int_role_id = role_id.isdigit() and int(role_id)
                                            role = discord.utils.find(lambda r: ((int_role_id and r.id == int_role_id) or r.name == role_id) and not r.managed, guild.roles)

                                            if not allow_old_roles and role and role in author.roles:
                                                remove_roles.add(role)

                if group_roles and group_ids:
                    for group_id, group_data in group_ids.items():
                        group_nickname = group_data.get("nickname")
                        bind_remove_roles = group_data.get("removeRoles") or []

                        if group_id != "0":
                            group = roblox_user.groups.get(str(group_id))

                            if group:
                                await group.apply_rolesets()
                                group_role = discord.utils.find(lambda r: r.name == group.user_rank_name and not r.managed, guild.roles)

                                if not group_role:
                                    if guild_data.get("dynamicRoles", DEFAULTS.get("dynamicRoles")):
                                        try:
                                            group_role = await guild.create_role(name=group.user_rank_name)
                                        except discord.errors.Forbidden:
                                            raise PermissionError(f"Sorry, I wasn't able to create the role {group.user_rank_name}."
                                                                   "Please ensure I have the `Manage Roles` permission.")

                                        except discord.errors.HTTPException:
                                            raise Error("Unable to create role: this server has reached the max amount of roles!")

                                for _, roleset_data in group.rolesets.items():
                                    has_role = discord.utils.find(lambda r: r.name == roleset_data[0] and not r.managed, author.roles)

                                    if has_role:
                                        if not allow_old_roles and group.user_rank_name != roleset_data[0]:
                                            remove_roles.add(has_role)

                                if group_role:
                                    add_roles.add(group_role)

                                    for role_id in bind_remove_roles:
                                        int_role_id = role_id.isdigit() and int(role_id)
                                        role = discord.utils.find(lambda r: ((int_role_id and r.id == int_role_id) or r.name == role_id) and not r.managed, author.roles)

                                        if role:
                                            remove_roles.add(role)

                                if nickname and group_nickname and group_role:
                                    if author.top_role == group_role and group_nickname:
                                        top_role_nickname = await self.get_nickname(author=author, group=group, template=group_nickname, roblox_user=roblox_user, user_data=author_data, dm=dm, response=response)

                                    if group_nickname and group_nickname != "skip":
                                        resolved_nickname = await self.get_nickname(author=author, group=group, template=group_nickname, roblox_user=roblox_user, user_data=author_data, dm=dm, response=response)

                                        if resolved_nickname and not resolved_nickname in possible_nicknames:
                                            possible_nicknames.append([group_role, resolved_nickname])
                            else:
                                try:
                                    group = await self.get_group(group_id, full_group=False)
                                except RobloxNotFound:
                                    raise Error(f"Error for linked group bind: group `{group_id}` not found")

                                for _, roleset_data in group.rolesets.items():
                                    group_role = discord.utils.find(lambda r: r.name == roleset_data[0] and not r.managed, author.roles)

                                    if not allow_old_roles and group_role:
                                        remove_roles.add(group_role)

        if roles:
            remove_roles = remove_roles.difference(add_roles)
            add_roles = add_roles.difference(author.roles)

            try:
                if add_roles:
                    await author.add_roles(*add_roles, reason="Adding group roles")

                if remove_roles:
                    await author.remove_roles(*remove_roles, reason="Removing old roles")

            except discord.errors.Forbidden:
                raise PermissionError("I was unable to sufficiently add roles to the user. Please ensure that "
                                      "I have the `Manage Roles` permission, and drag my role above the other roles. "
                                      f"{BIND_ROLE_BUG}")

            except discord.errors.NotFound:
                raise CancelCommand

        if nickname:
            if not unverified:
                if possible_nicknames:
                    if len(possible_nicknames) == 1:
                        nickname = possible_nicknames[0][1]
                    else:
                        # get highest role with a nickname
                        highest_role = sorted(possible_nicknames, key=lambda e: e[0].position, reverse=True)

                        if highest_role:
                            nickname = highest_role[0][1]
                else:
                    nickname = top_role_nickname or await self.get_nickname(template=guild_data.get("nicknameTemplate", DEFAULTS.get("nicknameTemplate")), author=author, user_data=author_data, roblox_user=roblox_user, dm=dm, response=response)

                if isinstance(nickname, bool):
                    nickname = self.get_nickname(template=guild_data.get("nicknameTemplate", DEFAULTS.get("nicknameTemplate")), roblox_user=roblox_user, author=author, user_data=author_data, dm=dm, response=response)

            if nickname and nickname != author.display_name:
                try:
                    await author.edit(nick=nickname)
                except discord.errors.Forbidden:
                    if guild.owner_id == author.id:
                        warnings.append("Since you're the Server Owner, I cannot edit your nickname. You may ignore this message; verification will work for normal users.")
                    else:
                        errors.append(f"I was unable to edit your nickname. Please ensure I have the `Manage Nickname` permission, and drag my role above the other roles. See: {BIND_ROLE_BUG}")
                except discord.errors.NotFound:
                    raise CancelCommand

        if unverified:
            raise UserNotVerified

        if not roblox_user:
            roblox_user, _ = await self.get_user(author=author, guild=guild, everything=True, author_data=author_data)

        return [r.name for r in add_roles], [r.name for r in remove_roles], nickname, errors, warnings, roblox_user

    async def get_group_shout(self, group_id):
        """gets the group shout. not cached."""

        text, response = await fetch(f"https://groups.roblox.com/v1/groups/{group_id}", raise_on_failure=False)

        if response.status == 404:
            raise RobloxNotFound

        elif response.status >= 500:
            raise RobloxDown

        try:
            response = json.loads(text)
            return response

        except json.decoder.JSONDecodeError:
            return {}

    @staticmethod
    async def get_game(game_id=None, game_name=None):
        if not (game_id or game_name):
            raise BadUsage("Must supply a game ID or game name to get_game")

        game = await cache_get(f"games:{game_id or game_name}")

        if game:
            return game

        if game_id:
            json_data, _ = await fetch(f"{API_URL}/marketplace/productinfo?assetId={game_id}", json=True, raise_on_failure=False)

            if json_data.get("AssetTypeId", 0) == 9:
                game = Game(str(game_id), json_data)

                await cache_set(f"games:{game_id}", game)

                return game
        else:
            json_data, _ = await fetch(f"https://games.roblox.com/v1/games/list?model.keyword={game_name}", json=True, raise_on_failure=False)

            if json_data.get("games"):
                game_data = json_data["games"][0]
                game = Game(str(game_data["placeId"]), game_data)


        raise RobloxNotFound

    @staticmethod
    async def get_catalog_item(item_id):
        item_id = str(item_id)
        item = await cache_get(f"catalog_items:{item_id}")

        if item:
            return item

        json_data, _ = await fetch(f"{API_URL}/marketplace/productinfo?assetId={item_id}", json=True, raise_on_failure=False)

        if json_data.get("AssetTypeId", 0) != 6:
            item = RobloxItem(item_id, json_data)

            await cache_set(f"catalog_items:{item_id}", item)

            return item


        raise RobloxNotFound


    @staticmethod
    async def get_group(group_id, full_group=False):
        group_id = str(group_id)

        if not group_id.isdigit():
            regex_search_group = roblox_group_regex.search(group_id)

            if regex_search_group:
                group_id = regex_search_group.group(1)

        group = await cache_get(f"groups:{group_id}")

        if group:
            if full_group:
                if group.name:
                    return group
            else:
                return group

        json_data, roleset_response = await fetch(f"{GROUP_API}/v1/groups/{group_id}/roles", json=True, raise_on_failure=False)

        if roleset_response.status == 200:
            if full_group:
                group_data, group_data_response = await fetch(f"{GROUP_API}/v1/groups/{group_id}", json=True, raise_on_failure=False)

                if group_data_response.status == 200:
                    json_data.update(group_data)

                emblem_data, emblem_data_response = await fetch(f"{THUMBNAIL_API}/v1/groups/icons?groupIds={group_id}&size=150x150&format=Png&isCircular=false", json=True, raise_on_failure=False)

                if emblem_data_response.status == 200:
                    emblem_data = emblem_data.get("data")

                    if emblem_data:
                        emblem_data = emblem_data[0]
                        json_data.update({"imageUrl": emblem_data.get("imageUrl")})

            if not group:
                group = Group(group_id=group_id, group_data=json_data)
            else:
                group.load_json(json_data)

            await cache_set(f"groups:{group_id}", group)

            return group

        elif roleset_response.status >= 500:
            raise RobloxDown

        raise RobloxNotFound


    @on_exception(expo, RateLimitException, max_tries=8)
    @limits(calls=30, period=30)
    async def call_bloxlink_api(self, author, guild=None):
        roblox_account = primary_account = None

        bloxlink_api = guild and f"https://api.blox.link/v1/user/{author.id}?guild={guild.id}" or f"https://api.blox.link/v1/user/{author.id}"
        author_verified_data, _ = await fetch(bloxlink_api, raise_on_failure=False)

        if not author_verified_data.get("error"):
            roblox_account = author_verified_data.get("matchingAccount") or author_verified_data.get("primaryAccount")
            primary_account = author_verified_data.get("primaryAccount")


        return roblox_account, primary_account


    async def get_user(self, *args, author=None, guild=None, username=None, roblox_id=None, author_data=None, everything=False, basic_details=True, group_ids=None, send_embed=False, send_ephemeral=False, response=None, cache=True) -> Tuple:
        guild = guild or getattr(author, "guild", False)
        guild_id = guild and str(guild.id)

        roblox_account = discord_profile = None
        accounts = []
        embed = None

        if send_embed:
            if not response:
                raise BadUsage("Must supply response object for embed sending")

            embed = [discord.Embed(title="Loading..."), response]

        if author:
            author_id = str(author.id)
            author_data = author_data or await self.r.db("bloxlink").table("users").get(author_id).run() or {}

            if cache:
                discord_profile = await cache_get(f"discord_profiles:{author_id}")

                if discord_profile:
                    if guild:
                        roblox_account = discord_profile.guilds.get(guild_id)
                    else:
                        roblox_account = discord_profile.primary_account

                    if roblox_account:
                        await roblox_account.sync(*args, author=author, group_ids=group_ids, embed=embed, response=response, send_ephemeral=send_ephemeral, guild=guild, everything=everything, basic_details=basic_details)

                        return roblox_account, discord_profile.accounts


            roblox_accounts = author_data.get("robloxAccounts", {})
            accounts = roblox_accounts.get("accounts", [])
            guilds = roblox_accounts.get("guilds", {})

            roblox_account = guild and guilds.get(guild_id) or author_data.get("robloxID")
            primary_account = author_data.get("robloxID")

            if SELF_HOST and not (roblox_account or primary_account):
                try:
                    roblox_account, primary_account = await self.call_bloxlink_api(author, guild)
                except RateLimitException:
                    pass

            if roblox_account:
                if not discord_profile:
                    discord_profile = DiscordProfile(author_id)

                    if primary_account:
                        discord_profile.primary_account = RobloxUser(roblox_id=primary_account)

                        if roblox_account != primary_account:
                            await discord_profile.primary_account.sync()


                    discord_profile.accounts = accounts

                roblox_user = None

                if cache:
                    roblox_user = await cache_get(f"roblox_users:{roblox_account}")

                roblox_user = roblox_user or RobloxUser(roblox_id=roblox_account)
                await roblox_user.sync(*args, author=author, group_ids=group_ids, embed=embed, send_ephemeral=send_ephemeral, response=response, guild=guild, everything=everything, basic_details=basic_details)

                if guild:
                    discord_profile.guilds[guild_id] = roblox_user

                if cache:
                    await cache_set(f"discord_profiles:{author_id}", discord_profile)
                    await cache_set(f"roblox_users:{roblox_account}", roblox_user)

                return roblox_user, accounts

            else:
                if accounts:
                    return None, accounts
                else:
                    raise UserNotVerified
        else:
            if not (roblox_id or username):
                raise BadUsage("Must supply a username or ID")

            if not roblox_id:
                roblox_id, username = await self.get_roblox_id(username)

            if roblox_id:
                roblox_user = await cache_get(f"roblox_users:{roblox_id}")

                if not roblox_user:
                    roblox_user = RobloxUser(roblox_id=roblox_id)

                    if cache:
                        await cache_set(f"roblox_users:{roblox_id}", roblox_user)

                await roblox_user.sync(*args, author=author, group_ids=group_ids, response=response, embed=embed, send_ephemeral=send_ephemeral, guild=guild, everything=everything, basic_details=basic_details)
                return roblox_user, []

            raise BadUsage("Unable to resolve a user")

    async def verify_as(self, author, guild=None, *, author_data=None, primary=False, trello_options=None, update_user=True, trello_board=None, response=None, guild_data=None, username=None, roblox_id=None, dm=True, cache=True) -> bool:
        if not (username or roblox_id):
            raise BadUsage("Must supply either a username or roblox_id to verify_as.")

        try:
            guild = guild or author.guild

            author_id = str(author.id)
            author_data = author_data or await self.r.db("bloxlink").table("users").get(author_id).run() or {}
            guild_data = guild_data or (guild and await self.r.table("guilds").get(str(guild.id)).run()) or {}

            allow_reverify = guild_data.get("allowReVerify", DEFAULTS.get("allowReVerify"))

            trello_options = trello_options or {}

            if not trello_options and trello_board:
                trello_options, _ = await get_options(trello_board)
                guild_data.update(trello_options)

            invalid_roblox_names = 0

            while not roblox_id:
                try:
                    roblox_id, username = await self.get_roblox_id(username)
                except RobloxNotFound:
                    if response:
                        message = await response.error("There was no Roblox account found with your query.\n"
                                                    "Please try again.", dm=dm, no_dm_post=True)

                        username = (await response.prompt([{
                            "prompt": "Please specify your Roblox username.",
                            "name": "username"
                        }], dm=dm, no_dm_post=True))["username"]

                        response.delete(message)

                    invalid_roblox_names += 1

                if invalid_roblox_names == 5:
                    raise Error("Too many invalid attempts. Please try again later.")

            if not username:
                roblox_id, username = await self.get_roblox_username(roblox_id)

            roblox_accounts = author_data.get("robloxAccounts", {})

            if guild and not allow_reverify:
                guild_accounts = roblox_accounts.get("guilds", {})
                chosen_account = guild_accounts.get(str(guild.id))

                if chosen_account and chosen_account != roblox_id:
                    raise Error("You already selected your account for this server. `allowReVerify` must be "
                                "enabled for you to change it.")

            if roblox_id in roblox_accounts.get("accounts", []) or author_data.get("robloxID") == roblox_id:
                # TODO: clear cache
                await self.verify_member(author, roblox_id, guild=guild, author_data=author_data, allow_reverify=allow_reverify, primary_account=primary)

                if update_user:
                    try:
                        await self.update_member(
                            author,
                            guild       = guild,
                            roles       = True,
                            nickname    = True,
                            author_data = author_data,
                            cache       = cache,
                            response    = response)

                    except (BloxlinkBypass, Blacklisted):
                        pass

                return username

            else:
                # prompts
                failures = 0
                failed = False

                if response:
                    args = await response.prompt([
                        {
                            "prompt": f"Welcome, **{username}!** Please select a method of verification:\n"
                                    "`game` " + ARROW + " verify by joining a Roblox game\n"
                                    "`code` " + ARROW + " verify by putting a code on your Roblox status or description",
                            "type": "choice",
                            "choices": ["game", "code"],
                            "name": "verification_choice"
                        }
                    ], dm=dm, no_dm_post=True)

                    if args["verification_choice"] == "code":
                        code = self.generate_code()

                        msg1 = await response.send("To confirm that you own this Roblox account, please put this code in your description or status:", dm=dm, no_dm_post=True)
                        msg2 = await response.send(f"```{code}```", dm=dm, no_dm_post=True)

                        response.delete(msg1, msg2)

                        _ = await response.prompt([{
                            "prompt": "Then, say `done` to continue.",
                            "name": "verification_next",
                            "type": "choice",
                            "choices": ["done"]
                        }], embed=False, dm=dm, no_dm_post=True)

                        if await self.validate_code(roblox_id, code):
                            # user is now validated; add their roles
                            await self.verify_member(author, roblox_id, allow_reverify=allow_reverify, guild=guild, author_data=author_data, primary_account=primary)

                            return username

                        while not await self.validate_code(roblox_id, code):
                            if failures == 5:
                                failed = True
                                break

                            failures += 1

                            _ = await response.prompt([
                                {
                                    "prompt": "Unable to find the code on your profile. Please say `done` to search again or `cancel` to cancel.",
                                    "type": "choice",
                                    "choices": ["done"],
                                    "name": "retry"
                                }
                            ], error=True, dm=dm, no_dm_post=True)

                            attempt = await self.validate_code(roblox_id, code)

                            if attempt:
                                await self.verify_member(author, roblox_id, allow_reverify=allow_reverify, author_data=author_data, guild=guild, primary_account=primary)

                                return username

                        if failed:
                            raise Error(f"{author.mention}, too many failed attempts. Please run this command again and retry.")

                    elif args["verification_choice"] == "game":
                        await self.r.db("bloxlink").table("gameVerification").insert({
                            "id": roblox_id,
                            "discordTag": str(author),
                            "discordID": str(author.id),
                            "primary": primary,
                            "guild": guild and str(guild.id),
                            "prefix": "!" #FIXME
                        }, conflict="replace").run()

                        _ = await response.prompt([{
                            "prompt": "Please go to this game https://www.roblox.com/games/1271943503/- to complete the verification process. Then, say `done` to "
                                    "get your roles.",
                            "name": "verification_next",
                            "type": "choice",
                            "choices": ["done"]
                        }], dm=dm, no_dm_post=True)

                        while True:
                            if failures == 5:
                                failed = True
                                break

                            try:
                                _, accounts = await self.get_user(author=author, cache=False)

                                if not roblox_id in accounts:
                                    raise UserNotVerified

                            except UserNotVerified:
                                _ = await response.prompt([{
                                    "prompt": "It appears that you didn't pass verification via the Roblox game. Please go to "
                                            "https://www.roblox.com/games/1271943503/- and try again. Then, say `done`.",
                                    "name": "verification_next",
                                    "type": "choice",
                                    "choices": ["done"]
                                }], error=True, dm=dm, no_dm_post=True)

                                failures += 1

                            else:
                                # await self.verify_member(author, roblox_id, allow_reverify=allow_reverify, author_data=author_data, guild=guild, primary_account=primary)
                                return username


                        if failed:
                            raise Error(f"{author.mention}, too many failed attempts. Please run this command again and retry.")
        finally:
            await cache_pop(f"discord_profiles:{author_id}")


    @staticmethod
    async def apply_perks(roblox_user, embed, guild=None, groups=False, author=None, tags=False):
        if not embed:
            return

        user_tags = []
        user_notable_groups = {}
        username_emotes_ = set()
        username_emotes = ""

        if roblox_user:
            if tags:
                for special_title, special_group in EMBED_PERKS["GROUPS"].items():
                    group = roblox_user.groups.get(special_group[0])

                    if group:
                        if special_group[1] and ((special_group[1] < 0 and group.user_rank_id < abs(special_group[1])) or (special_group[1] > 0 and group.user_rank_id != special_group[1])):
                            continue

                        user_tags.append(special_title)

                        if special_group[2]:
                            if guild:
                                if guild.default_role.permissions.external_emojis:
                                    username_emotes_.add(special_group[2])
                                else:
                                    if special_group[3]:
                                        username_emotes_.add(special_group[3])
                            else:
                                username_emotes_.add(special_group[2])

            username_emotes = "".join(username_emotes_)

            if username_emotes:
                for i, field in enumerate(embed.fields):
                    if field.name == "Username":
                        embed.set_field_at(i, name="Username", value=f"{username_emotes} {field.value}")

                        break

            if groups:
                all_notable_groups = await cache_get("partners:notable_groups", primitives=True, redis_hash=True) or {}
                user_notable_groups = {}

                for notable_group_id, notable_title in all_notable_groups.items():
                    notable_group_id = notable_group_id.decode('utf-8')
                    notable_title    = notable_title.decode('utf-8')

                    group = roblox_user.groups.get(notable_group_id)

                    if group:
                        user_notable_groups[group.group_id] = (group, notable_title)

        if guild and embed:
            cache_partner = await cache_get(f"partners:guilds:{guild.id}", primitives=True, redis_hash=True)
            verified_reaction = guild.default_role.permissions.external_emojis and REACTIONS["VERIFIED"] or ":white_check_mark:"

            if cache_partner:
                embed.description = f"{verified_reaction} This is an **official server** of [{cache_partner.get(b'group_name', 'N/A').decode('utf-8')}](https://www.roblox.com/groups/{cache_partner.get(b'group_id').decode('utf-8')}/-)"
                embed.colour = PARTNERED_SERVER

        if tags and author:
            if await cache_get(f"partners:users:{author.id}", primitives=True):
                user_tags.append("Bloxlink Partner")
                embed.colour = PARTNERS_COLOR

        return user_tags, user_notable_groups


@Bloxlink.module
class RobloxProfile(Bloxlink.Module):
    def __init__(self):
        pass

    @staticmethod
    async def get_inactive_role(guild, guild_data, trello_board):
        donator_profile, _ = await get_features(discord.Object(id=guild.owner_id), guild=guild)
        is_prem = donator_profile.features.get("premium")
        inactive_role = None

        if is_prem:
            if trello_board:
                options_trello_data, _ = await get_options(trello_board)
                inactive_role_trello = options_trello_data.get("inactiveRole")

                if inactive_role_trello:
                    inactive_role_id = inactive_role_trello.isdigit() and int(inactive_role_trello)
                    inactive_role = discord.utils.find(lambda r: ((inactive_role_id and r.id == inactive_role_id) or (r.name == inactive_role_trello)) and not r.managed, guild.roles)
            else:
                inactive_role_id = guild_data.get("inactiveRole")

                if inactive_role_id:
                    inactive_role_id = int(inactive_role_id)
                    inactive_role = discord.utils.find(lambda r: r.id == inactive_role_id and not r.managed, guild.roles)

        return inactive_role

    @staticmethod
    async def handle_inactive_role(inactive_role, user, inactive):
        if not inactive_role:
            return

        if inactive:
            if inactive_role not in user.roles:
                try:
                    await user.add_roles(inactive_role, reason="Adding inactive role")
                except discord.errors.Forbidden:
                    raise Error("I was unable to add the inactivity role! Please ensure I have the "
                                f"`Manage Roles` permission, and drag my roles above the other roles. {BIND_ROLE_BUG}")
                except discord.errors.NotFound:
                    pass
        else:
            if inactive_role in user.roles:
                try:
                    await user.remove_roles(inactive_role, reason="Removing inactive role")
                except discord.errors.Forbidden:
                    raise Error("I was unable to remove the inactivity role! Please ensure I have the "
                                f"`Manage Roles` permission, and drag my roles above the other roles. {BIND_ROLE_BUG}")
                except discord.errors.NotFound:
                    pass

    async def get_profile(self, author, user, roblox_user=None, prefix=None, guild=None, guild_data=None, inactive_role=None):
        user_data = await self.r.db("bloxlink").table("users").get(str(user.id)).run() or {"id": str(user.id)}
        profile_data = user_data.get("profileData") or {}
        prefix = prefix or PREFIX
        guild = guild or getattr(author, "guild", None)

        if guild:
            guild_data = guild_data or (await self.r.table("guilds").get(str(guild.id)).run()) or {}

        if roblox_user:
            ending = roblox_user.username.endswith("s") and "'" or "'s"
            embed = discord.Embed(title=f"{roblox_user.username}{ending} Bloxlink Profile")
            embed.set_author(name=user, icon_url=user.avatar.url, url=roblox_user.profile_link)
        else:
            embed = discord.Embed(title="Bloxlink User Profile")
            embed.set_author(name=user, icon_url=user.avatar.url)

        if not profile_data:
            await self.handle_inactive_role(inactive_role, user, False)

            if author == user:
                embed.description = f"You have no profile available! Use `{prefix}profile change` to make your profile."
            else:
                embed.description = f"**{user}** has no profile available."

            return embed

        description       = profile_data.get("description")
        activity_notice   = profile_data.get("activityNotice")
        favorite_games    = profile_data.get("favoriteGames")
        favorite_items    = profile_data.get("favoriteCatalogItems")
        accepting_trades  = profile_data.get("acceptingTrades")

        set_embed_desc = False

        if activity_notice:
            if isinstance(activity_notice, dict): # TODO: delete this after all notices are converted
                return_timestamp  = activity_notice["returnTimestamp"]
                inactivity_reason = activity_notice["reason"]
            else:
                return_timestamp = activity_notice
                inactivity_reason = None

            date = datetime.fromtimestamp(return_timestamp)
            time_now = datetime.now()

            if time_now > date:
                # user is back

                if guild:
                    await post_event(guild, guild_data, "inactivity notice", f"{author.mention} is now **back** from their leave of absence.", PURPLE_COLOR)

                await self.handle_inactive_role(inactive_role, user, False)

                profile_data.pop("activityNotice")
                user_data["profileData"] = profile_data

                await self.r.db("bloxlink").table("users").insert(user_data, conflict="replace").run()
            else:
                await self.handle_inactive_role(inactive_role, user, True)

                date_str = date.strftime("%b. %d, %Y (%A)")

                if inactivity_reason:
                    date_formatted = f"This user is currently **away** until **{date_str}** for: `{inactivity_reason}`"
                else:
                    date_formatted = f"This user is currently **away** until **{date_str}.**"

                embed.description = date_formatted
                embed.colour = ORANGE_COLOR

                set_embed_desc = True
        else:
            await self.handle_inactive_role(inactive_role, user, False)

        if accepting_trades:
            if set_embed_desc:
                embed.description = f"{embed.description}\nThis user is **accepting trades.**"
            else:
                embed.description = "This user is **accepting trades.**"

        if favorite_games:
            desc = []

            for game_id in favorite_games:
                try:
                    game = await Roblox.get_game(game_id)
                except (RobloxNotFound, RobloxAPIError):
                    desc.append(f"**INVALID GAME:** {game_id}")
                else:
                    desc.append(f"[{game.name}]({game.url})")

            if desc:
                embed.add_field(name="Favorite Games", value="\n".join(desc))

        if favorite_items:
            desc = []

            for item_id in favorite_items:
                try:
                    catalog_item = await Roblox.get_catalog_item(item_id)
                except (RobloxNotFound, RobloxAPIError):
                    desc.append(f"**INVALID ITEM:** {item_id}")
                else:
                    desc.append(f"[{catalog_item.name}]({catalog_item.url})")

            if desc:
                embed.add_field(name="Favorite Catalog Items", value="\n".join(desc))

        if description:
            embed.add_field(name="Personal Description", value=description, inline=False)


        if author == user:
            embed.set_footer(text=f"Use \"{prefix}profile change\" to alter your profile.")

        return embed

    @staticmethod # needs to be static
    async def is_inactive(user, inactive_role, user_data=None):
        if not inactive_role:
            return

        user_data = user_data or await RobloxProfile.r.db("bloxlink").table("users").get(str(user.id)).run() or {"id": str(user.id)}
        profile_data = user_data.get("profileData") or {}
        activity_notice = profile_data.get("activityNotice")

        if activity_notice:
            if isinstance(activity_notice, dict): # TODO: delete this after all notices are converted
                return_timestamp  = activity_notice["returnTimestamp"]
            else:
                return_timestamp = activity_notice

            date = datetime.fromtimestamp(return_timestamp)
            time_now = datetime.now()

            if time_now > date:
                # user is back

                profile_data.pop("activityNotice")
                user_data["profileData"] = profile_data

                await RobloxProfile.r.db("bloxlink").table("users").insert(user_data, conflict="replace").run()

                return False

            else:
                return True
        else:
            return False


class DiscordProfile:
    __slots__ = ("id", "primary_account", "accounts", "guilds")

    def __init__(self, author_id, **kwargs):
        self.id = author_id

        self.primary_account = kwargs.get("primary_account")
        self.accounts = kwargs.get("accounts", [])
        self.guilds = kwargs.get("guilds", {})

    def __eq__(self, other):
        return self.id == getattr(other, "id", None)

class Group(Bloxlink.Module):
    __slots__ = ("name", "group_id", "description", "rolesets", "owner", "member_count",
                 "emblem_url", "url", "user_rank_name", "user_rank_id", "shout")

    def __init__(self, group_id, group_data, my_roles=None):
        numeric_filter = filter(str.isdigit, str(group_id))
        self.group_id = "".join(numeric_filter)

        self.name = None
        self.description = None
        self.owner = None
        self.member_count = None
        self.emblem_url = None
        self.rolesets = {}
        self.url = f"https://www.roblox.com/groups/{self.group_id}"
        self.shout = None

        self.user_rank_name = None
        self.user_rank_id = None

        self.load_json(group_data, my_roles=my_roles)

    async def apply_rolesets(self):
        if self.rolesets:
            return

        group_data, roleset_response = await fetch(f"{GROUP_API}/v1/groups/{self.group_id}/roles", json=True)

        if roleset_response.status == 200:
            self.load_json(group_data)

        elif roleset_response.status >= 500:
            raise RobloxDown

    def load_json(self, group_data, my_roles=None):
        self.shout = group_data.get("shout") or self.shout
        self.emblem_url = self.emblem_url or group_data.get("imageUrl")

        self.name = self.name or group_data.get("name") or group_data.get("Name", "")
        self.member_count = self.member_count or group_data.get("memberCount", 0)
        self.description = self.description or group_data.get("description") or group_data.get("Description", "")

        self.user_rank_name = self.user_rank_name or (my_roles and my_roles.get("name", "").strip())
        self.user_rank_id = self.user_rank_id or (my_roles and my_roles.get("rank"))

        self.owner = self.owner or group_data.get("owner")

        if not self.rolesets and (group_data.get("roles") or group_data.get("Roles")):
            rolesets = group_data.get("roles") or group_data.get("Roles")

            for roleset in reversed(rolesets):
                roleset_id = roleset.get("rank") or roleset.get("Rank")
                roleset_name = roleset.get("name").strip()

                if roleset_id:
                    self.rolesets[roleset_name.lower()] = [roleset_name, int(roleset_id)]

    def __str__(self):
        return f"Group ({self.name or self.group_id})"

    def __repr__(self):
        return self.__str__()

class RobloxItem:
    __slots__ = ("item_id", "name", "description", "url", "owner", "created")

    def __init__(self, item_id, item_data):
        self.item_id = str(item_id)
        self.name = None
        self.description = None
        self.owner = None
        self.url = None
        self.created = None

        self.load_json(item_data)

    def load_json(self, item_data):
        self.name = self.name or item_data.get("Name")
        self.description = self.description or item_data.get("Description")
        self.owner = self.owner or item_data.get("Creator")
        self.created = self.created or item_data.get("Created")
        self.url = self.url or f"https://www.roblox.com/catalog/{self.item_id}/-"


class Game(RobloxItem):
    def __init__(self, game_id, game_data):
        super().__init__(game_id, game_data)

        self.url = f"https://www.roblox.com/games/{self.item_id}/-"
        self.group_game = False
        self.creator_name = ""
        self.up_votes = 0
        self.down_votes = 0
        self.player_count = 0

        #self.load_json(game_data)
    """
    def load_json(self, data):
        self.group_game   = data.get("creatorType") == "Group"
        self.up_votes     = self.up_votes or data.get("totalUpVotes")
        self.down_votes   = self.down_votes or data.get("totalDownVotes")
        self.player_count = self.player_count or data.get("playerCount")
    """


    def __str__(self):
        return f"Game ({self.name or self.item_id})"

    def __repr__(self):
        return self.__str__()


class RobloxUser(Bloxlink.Module):
    __slots__ = ("username", "id", "discord_id", "verified", "complete", "more_details", "groups",
                 "avatar", "premium", "presence", "badges", "description", "banned", "age", "created",
                 "join_date", "profile_link", "session", "embed", "dev_forum", "display_name", "full_join_string")

    def __init__(self, *, username=None, roblox_id=None, discord_id=None, **kwargs):
        self.username = username
        self.id = roblox_id
        self.discord_id = discord_id

        self.verified = False
        self.complete = False
        self.more_details = False
        self.partial = False

        self.groups = kwargs.get("groups", {})
        self.avatar = kwargs.get("avatar")
        self.premium = kwargs.get("premium", False)
        self.presence = kwargs.get("presence")
        self.badges = kwargs.get("badges", [])
        self.description = kwargs.get("description", "")
        self.banned = kwargs.get("banned", False)
        self.created =  kwargs.get("created", None)
        self.dev_forum =  kwargs.get("dev_forum", None)
        self.display_name =  kwargs.get("display_name", username)

        self.embed = None

        self.age = 0
        self.join_date = None
        self.full_join_string = None
        self.profile_link = roblox_id and f"https://www.roblox.com/users/{roblox_id}/profile"

    @staticmethod
    async def get_details(*args, author=None, username=None, roblox_id=None, everything=False, basic_details=False, roblox_user=None, group_ids=None, response=None, guild=None, embed=None, send_ephemeral=False):
        if everything:
            basic_details = True

        roblox_data = {
            "username": username,
            "display_name": None,
            "id": roblox_id,
            "groups": None,
            "presence": None,
            "premium": None,
            "badges": None,
            "avatar": None,
            "profile_link": roblox_id and f"https://www.roblox.com/users/{roblox_id}/profile",
            "banned": None,
            "description": None,
            "age": None,
            "join_date": None,
            "full_join_string": None,
            "created": None,
            "dev_forum": None
        }


        if group_ids:
            group_ids[0].update(group_ids[1].get("groups", {}.keys()))
            group_ids = group_ids[0]

        roblox_user_from_cache = None

        if username:
            cache_find = await cache_get(f"usernames_to_ids:{username}")

            if cache_find:
                roblox_id, username = cache_find

            if roblox_id:
                roblox_user_from_cache = await cache_get(f"roblox_users:{roblox_id}")

        if roblox_user_from_cache and roblox_user_from_cache.verified:
            roblox_data["id"] = roblox_id or roblox_user_from_cache.id
            roblox_data["username"] = username or roblox_user_from_cache.username
            roblox_data["display_name"] = roblox_user_from_cache.display_name
            roblox_data["groups"] = roblox_user_from_cache.groups
            roblox_data["avatar"] = roblox_user_from_cache.avatar
            roblox_data["premium"] = roblox_user_from_cache.premium
            roblox_data["presence"] = roblox_user_from_cache.presence
            roblox_data["badges"] = roblox_user_from_cache.badges
            roblox_data["banned"] = roblox_user_from_cache.banned
            roblox_data["join_date"] = roblox_user_from_cache.join_date
            roblox_data["full_join_string"] = roblox_user_from_cache.full_join_string
            roblox_data["description"] = roblox_user_from_cache.description
            roblox_data["age"] = roblox_user_from_cache.age
            roblox_data["created"] = roblox_user_from_cache.created
            roblox_data["dev_forum"] = roblox_user_from_cache.dev_forum

        if roblox_id and not username:
            roblox_id, username = await Roblox.get_roblox_username(roblox_id)
            roblox_data["username"] = username
            roblox_data["id"] = roblox_id

        elif not roblox_id and username:
            roblox_id, username = await Roblox.get_roblox_id(username)
            roblox_data["username"] = username
            roblox_data["id"] = roblox_id

        if not (username and roblox_id):
            return None

        if embed:
            if response:
                if not (response.webhook_only or send_ephemeral):
                    sent_embed = await embed[1].send(embed=embed[0])

                    if not sent_embed:
                        embed = None
                    else:
                        embed.append(sent_embed)

                if basic_details or "username" in args:
                    embed[0].add_field(name="Username", value=f"[@{username}]({roblox_data['profile_link']})")

                if basic_details or "id" in args:
                    embed[0].add_field(name="ID", value=roblox_id)

        if roblox_user:
            roblox_user.username = username
            roblox_user.id = roblox_id

        async def avatar():
            if roblox_data["avatar"] is not None:
                avatar_url = roblox_data["avatar"]
            else:
                avatar_url, _ = await fetch(f"{BASE_URL}/bust-thumbnail/json?userId={roblox_data['id']}&height=180&width=180", json=True)
                avatar_url = avatar_url.get("Url")

                if roblox_user:
                    roblox_user.avatar = avatar_url

                roblox_data["avatar"] = avatar_url

            if embed:
                embed[0].set_thumbnail(url=avatar_url)

                if author:
                    embed[0].set_author(name=str(author), icon_url=author.avatar.url, url=roblox_data.get("profile_link"))

        async def membership_and_badges():
            if roblox_data["premium"] is not None and roblox_data["badges"] is not None:
                premium = roblox_data["premium"]
                badges = roblox_data["badges"]
            else:
                premium = False
                badges = set()

                data, _ = await fetch(f"{BASE_URL}/badges/roblox?userId={roblox_data['id']}", json=True) # FIXME

                for badge in data.get("RobloxBadges", []):
                    badges.add(badge["Name"])

                roblox_data["badges"] = badges
                roblox_data["premium"] = premium

                if roblox_user:
                    roblox_user.badges = badges
                    roblox_user.premium = premium

            if embed:
                if premium:
                    #embed[0].add_field(name="Membership", value=membership)
                    #embed[0].title = f"<:robloxpremium:614583826538299394> {embed[0].title}"
                    # TODO
                    pass

                if (everything or "badges" in args) and badges:
                    embed[0].add_field(name="Badges", value=", ".join(badges))

        async def groups():
            if roblox_data["groups"] is not None:
                groups = roblox_data["groups"]
            else:
                groups = {}
                group_json, _ = await fetch(f"{GROUP_API}/v2/users/{roblox_data['id']}/groups/roles", json=True)

                for group_data in group_json.get("data", []):
                    group_data, my_roles = group_data.get("group"), group_data.get("role")
                    group_id = str(group_data["id"])
                    groups[group_id] = Group(group_id, group_data=group_data, my_roles=my_roles)

                if roblox_user:
                    roblox_user.groups = groups

            if embed and (everything or "groups" in args):
                group_ranks = set()
                _, notable_groups = await Roblox.apply_perks(roblox_user, groups=True, author=author, embed=embed and embed[0])
                notable_groups_str = []

                if group_ids and groups:
                    for group_id in group_ids:
                        group = groups.get(group_id)

                        if group:
                            if group.group_id in notable_groups:
                                notable_groups.pop(group.group_id)

                            group_ranks.add(f"[{group.name}]({group.url}) {ARROW} {group.user_rank_name}")

                    if group_ranks:
                        embed[0].add_field(name="Group Ranks", value=("\n".join(group_ranks)[:1000]), inline=False)

                if notable_groups:
                    all_notable_groups = list(notable_groups.values())

                    if all_notable_groups:
                        all_notable_groups.sort(key=lambda g: g[0].user_rank_id, reverse=True)
                        all_notable_groups = all_notable_groups[:4]

                        for notable_group in all_notable_groups:
                            notable_groups_str.append(f"[{notable_group[1]}]({notable_group[0].url}) {ARROW} {notable_group[0].user_rank_name}")

                    notable_groups_str = "\n".join(notable_groups_str)
                    embed[0].add_field(name="Notable Groups", value=notable_groups_str, inline=False)


        async def profile():
            banned = description = age = created = join_date = display_name = full_join_string = None

            if roblox_data["description"] is not None and roblox_data["age"] is not None and roblox_data["join_date"] is not None and roblox_data["created"] is not None and roblox_data["display_name"] is not None:
                description = roblox_data["description"]
                age = roblox_data["age"]
                join_date = roblox_data["join_date"]
                banned = roblox_data["banned"]
                created = roblox_data["created"]
                display_name = roblox_data["display_name"]
                full_join_string = roblox_data["full_join_string"]
            else:
                banned = None
                description = None
                age = None
                created = None
                join_date = None
                display_name = None
                full_join_string = None

                profile, _ = await fetch(f"https://users.roblox.com/v1/users/{roblox_data['id']}", json=True)

                description = profile.get("description")
                created = profile.get("created")
                banned = profile.get("isBanned")
                display_name = profile.get("displayName")

                roblox_data["description"] = description
                roblox_data["created"] = created
                roblox_data["banned"] = banned
                roblox_data["display_name"] = display_name

            if age is None:
                today = datetime.today()
                roblox_user_age = parser.parse(created).replace(tzinfo=None)
                age = (today - roblox_user_age).days

                join_date = f"{roblox_user_age.month}/{roblox_user_age.day}/{roblox_user_age.year}"

                roblox_data["age"] = age
                roblox_data["join_date"] = join_date

                if age >= 365:
                    years = math.floor(age/365)
                    ending = f"year{((years > 1 or years == 0) and 's') or ''}"
                    text = f"{years} {ending} old"
                else:
                    ending = f"day{((age > 1 or age == 0) and 's') or ''}"
                    text = f"{age} {ending} old"

                full_join_string = f"{text} ({join_date})"
                roblox_data["full_join_string"] = full_join_string

            if embed:
                if age and (everything or "age" in args):
                    embed[0].add_field(name="Account Age", value=roblox_data["full_join_string"])

                if banned and (everything or "banned" in args):
                    if guild and guild.default_role.permissions.external_emojis:
                        embed[0].description = f"{REACTIONS['BANNED']} This user is _banned._"
                    else:
                        embed[0].description = ":skull: This user is _banned._"

                    for i, field in enumerate(embed[0].fields):
                        if field.name == "Username":
                            if guild and guild.default_role.permissions.external_emojis:
                                embed[0].set_field_at(i, name="Username", value=f"{REACTIONS['BANNED']} ~~{roblox_data['username']}~~")
                            else:
                                embed[0].set_field_at(i, name="Username", value=f":skull: ~~{roblox_data['username']}~~")

                            break
                else:
                    if "banned" in args:
                        embed[0].description = "This user is not banned."

                if description and (everything or "description" in args):
                    embed[0].add_field(name="Description", value=description.replace("\n\n\n", "\n\n")[0:500], inline=False)

            if roblox_user:
                roblox_user.description = description
                roblox_user.age = age
                roblox_user.join_date = join_date
                roblox_user.full_join_string = full_join_string
                roblox_user.created = created
                roblox_user.banned = banned
                roblox_user.display_name = display_name

        async def dev_forum():
            dev_forum_profile = None
            trust_levels = {
                0: "No Access",
                1: "Member",
                2: "Regular",
                3: "Editor",
                4: "Leader"
            }

            if roblox_data["dev_forum"] is not None:
                dev_forum_profile = roblox_data["dev_forum"]
            else:
                try:
                    dev_forum_profile_, response = await fetch(f"https://devforum.roblox.com/u/by-external/{roblox_data['id']}.json", json=True, raise_on_failure=False, timeout=5, retry=0)

                    if response.status == 200:
                        dev_forum_profile = dev_forum_profile_.get("user")

                        roblox_data["dev_forum"] = dev_forum_profile

                        if roblox_user:
                            roblox_user.dev_forum = roblox_data["dev_forum"]

                except RobloxDown:
                    pass

            if embed and (everything or "dev_forum" in args or "devforum" in args):
                if dev_forum_profile and dev_forum_profile.get("trust_level"):
                    dev_forum_desc = (f"Trust Level: {trust_levels.get(dev_forum_profile['trust_level'], 'No Access')}\n"
                                     f"""{dev_forum_profile.get('title') and f'Title: {dev_forum_profile["title"]}' or ''}""")
                else:
                    dev_forum_desc = "This user isn't in the DevForums."

                if not args:
                    if dev_forum_profile and dev_forum_profile.get("trust_level"):
                        embed[0].add_field(name="DevForum", value=dev_forum_desc)
                else:
                    embed[0].description = dev_forum_desc


        if basic_details or "avatar" in args:
            await avatar()

        if basic_details or "groups" in args:
            await groups()

        if everything or "description" in args or "blurb" in args or "age" in args or "banned" in args:
            await profile()

        if everything or "premium" in args or "badges" in args:
            await membership_and_badges()

        if everything or "dev_forum" in args or "devforum" in args:
            await dev_forum()

        if embed:
            display_name = roblox_data["display_name"]

            if display_name:
                embed[0].title = display_name
            else:
                embed[0].title = username

            view = discord.ui.View()
            view.add_item(item=discord.ui.Button(style=discord.ButtonStyle.link, label="Visit Profile", url=roblox_data["profile_link"], emoji="👥"))

            if roblox_data["dev_forum"] and roblox_data["dev_forum"].get("trust_level"):
                view.add_item(item=discord.ui.Button(style=discord.ButtonStyle.link, label="Visit DevForum Profile", url=f"https://devforum.roblox.com/u/{roblox_data['dev_forum']['username']}", emoji="🧑‍💻"))

            if not args:
                user_tags, _ = await Roblox.apply_perks(roblox_user, author=author, tags=True, guild=guild, embed=embed and embed[0])

                if user_tags:
                    embed[0].add_field(name="User Tags", value="\n".join(user_tags))

            if response:
                if response.webhook_only or send_ephemeral:
                    await response.send(embed=embed[0], view=view, hidden=True)
                else:
                    await embed[2].edit(embed=embed[0], view=view)

        return roblox_data

    async def sync(self, *args, author=None, basic_details=True, group_ids=None, embed=None, send_ephemeral=False, response=None, guild=None, everything=False):
        try:
            await self.get_details(
                *args,
                username = self.username,
                roblox_id = self.id,
                everything = everything,
                basic_details = basic_details,
                embed = embed,
                send_ephemeral=send_ephemeral,
                group_ids = group_ids,
                roblox_user = self,
                author = author,
                response = response,
                guild = guild
            )

        except RobloxAPIError:
            traceback.print_exc()
            self.complete = False

            if self.discord_id and self.id:
                # TODO: set username from database
                self.partial = True # only set if there is a db entry for the user with the username
            else:
                raise
        else:
            self.complete = self.complete or everything
            self.verified = True
            self.partial = not everything
            self.profile_link = self.profile_link or f"https://www.roblox.com/users/{self.id}/profile"

    def __eq__(self, other):
        return self.id == getattr(other, "id", None) or self.username == getattr(other, "username", None)

    def __str__(self):
        return self.id