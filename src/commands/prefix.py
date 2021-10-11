from resources.structures.Bloxlink import Bloxlink # pylint: disable=import-error, no-name-in-module
from resources.exceptions import PermissionError # pylint: disable=import-error, no-name-in-module
from resources.constants import BROWN_COLOR, RELEASE, TRELLO # pylint: disable=import-error, no-name-in-module
from aiotrello.exceptions import TrelloUnauthorized, TrelloNotFound, TrelloBadRequest


get_prefix, post_event = Bloxlink.get_module("utils", attrs=["get_prefix", "post_event"])
set_guild_value = Bloxlink.get_module("cache", attrs=["set_guild_value"])

@Bloxlink.command
class PrefixCommand(Bloxlink.Module):
    """change or view your prefix used for commands"""

    def __init__(self):
        self.arguments = [
            {
                "prompt": "Please specify a new prefix.",
                "name": "new_prefix",
                "max": 10,
                "optional": True
            }
        ]
        self.examples = ["?"]

        permission = Bloxlink.Permissions().build("BLOXLINK_MANAGER")
        permission.allow_bypass = True

        self.permissions = permission
        self.category = "Administration"
        self.slash_enabled = True

    async def __main__(self, CommandArgs):
        response = CommandArgs.response

        author = CommandArgs.author

        guild = CommandArgs.guild
        guild_data = CommandArgs.guild_data

        new_prefix = CommandArgs.parsed_args.get("new_prefix")

        if new_prefix:
            if not CommandArgs.has_permission:
                raise PermissionError("You do not meet the required permissions for this command.")

            if RELEASE == "PRO":
                prefix_name = "proPrefix"
            else:
                prefix_name = "prefix"

            await self.r.table("guilds").insert({
                "id": str(guild.id),
                prefix_name: new_prefix
            }, conflict="update").run()

            trello_board = CommandArgs.trello_board

            if trello_board:
                _, card = await get_prefix(guild=guild, trello_board=trello_board)

                if card:
                    try:
                        if card.name == prefix_name:
                            await card.edit(desc=new_prefix)
                        else:
                            await card.edit(name=f"{prefix_name}:{new_prefix}")
                    except TrelloUnauthorized:
                        await response.error("In order for me to edit your Trello settings, please add `@bloxlink` to your "
                                             "Trello board.")
                    except (TrelloNotFound, TrelloBadRequest):
                        pass
                    else:
                        await trello_board.sync(card_limit=TRELLO["CARD_LIMIT"], list_limit=TRELLO["LIST_LIMIT"])

            await post_event(guild, guild_data, "configuration", f"{author.mention} ({author.id}) has **changed** the `prefix` option.", BROWN_COLOR)

            await set_guild_value(guild, prefix_name, new_prefix)

            await response.success("Your prefix was successfully changed!")

        else:
            old_prefix = CommandArgs.real_prefix

            await response.send(f"Your prefix used for Bloxlink: `{old_prefix}`.\n"
                                 "Change it with `@Bloxlink prefix <new prefix>`.")
