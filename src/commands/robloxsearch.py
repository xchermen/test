from resources.structures.Bloxlink import Bloxlink # pylint: disable=import-error, no-name-in-module, no-name-in-module
from resources.exceptions import Error, RobloxNotFound, RobloxAPIError, Message # pylint: disable=import-error, no-name-in-module, no-name-in-module
from discord.errors import NotFound

get_user, get_binds = Bloxlink.get_module("roblox", attrs=["get_user", "get_binds"])
parse_message = Bloxlink.get_module("commands", attrs=["parse_message"])


@Bloxlink.command
class RobloxSearchCommand(Bloxlink.Module):
    """retrieve the Roblox information of a user"""

    def __init__(self):
        self.aliases = ["rs", "search", "roblox-search"]
        self.arguments = [
            {
                "prompt": "Please specify either a username or Roblox ID. If the person's name is all numbers, "
                          "then attach a `--username` flag to this command. Example: `!getinfo 1234 --username` will "
                          "search for a user with a Roblox username of '1234' instead of a Roblox ID.",
                "slash_desc": "Please enter a Roblox username or Roblox ID.",
                "type": "string",
                "name": "roblox_name"
            }
        ]
        self.examples = [
            "roblox",
            "569422833",
            "569422833 --username"
        ]
        self.cooldown = 5
        self.dm_allowed = True
        self.slash_enabled = True
        self.slash_defer = True

    @Bloxlink.flags
    async def __main__(self, CommandArgs):
        target = CommandArgs.parsed_args["roblox_name"]
        flags = CommandArgs.flags
        response = CommandArgs.response
        message = CommandArgs.message
        guild = CommandArgs.guild
        prefix = CommandArgs.prefix

        if message and message.mentions and CommandArgs.string_args:
            message.content = f"{prefix}getinfo {CommandArgs.string_args[0]}"
            return await parse_message(message)

        valid_flags = ["username", "id", "avatar", "premium", "badges", "groups", "description", "age", "banned", "devforum"]

        if not all(f in valid_flags for f in flags.keys()):
            raise Error(f"Invalid flag! Valid flags are: `{', '.join(valid_flags)}`")

        username = ID = False

        if "username" in flags:
            username = True
            flags.pop("username")
        elif target.isdigit():
            ID = True
        else:
            username = True

        #async with response.loading():
        if guild:
            role_binds, group_ids, _ = await get_binds(guild_data=CommandArgs.guild_data, trello_board=CommandArgs.trello_board)
        else:
            role_binds, group_ids = {}, {}

        try:
            _, _ = await get_user(*flags.keys(), username=username and target, roblox_id=ID and target, group_ids=(group_ids, role_binds), send_embed=True, guild=guild, response=response, everything=not bool(flags), basic_details=not bool(flags))
        except RobloxNotFound:
            raise Error("This Roblox account doesn't exist.")
        except RobloxAPIError:
            if ID:
                try:
                    await Bloxlink.fetch_user(int(target))
                except NotFound:
                    raise Error("This Roblox account doesn't exist.")
                else:
                    if message:
                        message.content = f"{prefix}getinfo {target}"
                        return await parse_message(message)
                    else:
                        raise Message(f"To search with Discord IDs, please use the `{prefix}getinfo` command.\n"
                                      "This command only searches by Roblox username or ID.", hidden=True, type="info")
            else:
                raise Error("This Roblox account doesn't exist.")
