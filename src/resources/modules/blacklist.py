from ..structures import Bloxlink # pylint: disable=import-error, no-name-in-module
from ..constants import RELEASE # pylint: disable=import-error, no-name-in-module
from config import RESTRICTIONS_TRELLO # pylint: disable=import-error, no-name-in-module, no-name-in-module
from time import time
import re


trello = Bloxlink.get_module("trello", attrs="trello")
cache_set, cache_get, get_guild_value = Bloxlink.get_module("cache", attrs=["set", "get", "get_guild_value"])


@Bloxlink.module
class Blacklist(Bloxlink.Module):
    def __init__(self):
        self.option_regex = re.compile("(.+):(.+)")

        self.trello_board = None

    async def __setup__(self):
        await self.load_blacklist()

    async def get_restriction(self, type, id, guild=None, roblox_user=None):
        id = str(id)

        if guild:
            restrictions = await get_guild_value(guild, "restrictions")

            if restrictions:
                restriction = restrictions.get(type, {}).get(id, {})

                if restriction:
                    return restriction.get("reason") or "This server has restricted you from verifying."

                if roblox_user:
                    for restricted_group_id, restricted_group in restrictions.get("groups", {}).items():
                        group = roblox_user.groups.get(restricted_group_id)

                        if group:
                            return restricted_group.get("reason") or f"This server has prevented your group {group.name} from verifying."
        else:
            restriction = await cache_get(f"restrictions:global:{type}:{id}", primitives=True)

            if restriction is not None:
                if restriction:
                    return restriction

                return True

    async def parse_data(self, trello_list, directory):
        for card in await trello_list.get_cards():
            match = self.option_regex.search(card.name)

            if match:
                ID = match.group(2)
                desc = card.desc

                await cache_set(f"restrictions:global:{directory}:{ID}", desc, expire=43800)

    async def load_blacklist(self):
        if RELEASE in ("CANARY", "LOCAL"):
            """restricted_users = await self.r.db("bloxlink").table("restrictedUsers").run()

            time_now = (time()) * 1000 # for compatibility with the Javascript Bloxlink API

            async for restricted_user in restricted_users:
                restrictions = restricted_user["restrictions"]

                for i, restriction in enumerate(list(restrictions)):
                    if restriction["expiry"] <= time_now:
                        try:
                            restrictions.pop(i)
                            restricted_user["restrictions"] = restrictions

                            await self.r.db("bloxlink").table("restrictedUsers").insert(restricted_user, conflict="update").run()
                        except IndexError:
                            pass
                    else:
                        if restriction["type"] in ("global", "bot"):
                            await cache_set(f"restrictions:discord_ids:{restricted_user['id']}", restriction["reason"])

                if not restrictions:
                    await self.r.db("bloxlink").table("restrictedUsers").get(restricted_user["id"]).delete().run()
            """

            try:
                self.trello_board = await trello.get_board(RESTRICTIONS_TRELLO)
            except Exception:
                pass
            else:
                roblox_ids = await self.trello_board.get_list(lambda l: l.name == "Roblox Accounts")
                discord_ids = await self.trello_board.get_list(lambda l: l.name == "Discord Accounts")
                server_ids = await self.trello_board.get_list(lambda l: l.name == "Servers")

                await self.parse_data(roblox_ids, "robloxAccounts")
                await self.parse_data(discord_ids, "users")
                await self.parse_data(server_ids, "guilds")

