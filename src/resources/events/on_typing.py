from ..structures.Bloxlink import Bloxlink # pylint: disable=import-error, no-name-in-module
from discord import Member, Object
from discord.utils import find
from ..constants import DEFAULTS, RELEASE # pylint: disable=import-error, no-name-in-module
from ..exceptions import CancelCommand # pylint: disable=import-error, no-name-in-module

cache_get, cache_set, get_guild_value = Bloxlink.get_module("cache", attrs=["get", "set", "get_guild_value"])
guild_obligations = Bloxlink.get_module("roblox", attrs=["guild_obligations"])
get_board, get_options = Bloxlink.get_module("trello", attrs=["get_board", "get_options"])
get_features = Bloxlink.get_module("premium", attrs=["get_features"])
has_magic_role = Bloxlink.get_module("extras", attrs=["has_magic_role"])


@Bloxlink.module
class ChannelTypingEvent(Bloxlink.Module):
    def __init__(self):
        pass

    async def __setup__(self):

        @Bloxlink.event
        async def on_typing(channel, user, when):
            if isinstance(user, Member):
                guild = user.guild
                donator_profile, _ = await get_features(Object(id=guild.owner_id), guild=guild)

                if donator_profile.features.get("premium"):
                    if await cache_get(f"channel_typing:{guild.id}:{user.id}", primitives=True):
                        return

                    options = await get_guild_value(guild, ["persistRoles", DEFAULTS.get("persistRoles")], ["magicRoles", {}])
                    persist_roles = options["persistRoles"]
                    magic_roles   = options["magicRoles"]

                    if persist_roles:
                        await cache_set(f"channel_typing:{guild.id}:{user.id}", True, expire=7200)

                        if not has_magic_role(user, magic_roles, "Bloxlink Bypass"):
                            try:
                                await guild_obligations(user, guild, join=True, dm=False, event=False)
                            except CancelCommand:
                                pass
