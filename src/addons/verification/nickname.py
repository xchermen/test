from resources.structures.Bloxlink import Bloxlink # pylint: disable=import-error, no-name-in-module
from resources.exceptions import CancelledPrompt # pylint: disable=import-error, no-name-in-module
from resources.constants import ARROW, ESCAPED_NICKNAME_TEMPLATES, BROWN_COLOR # pylint: disable=import-error, no-name-in-module


post_event = Bloxlink.get_module("utils", attrs=["post_event"])
set_guild_value = Bloxlink.get_module("cache", attrs=["set_guild_value"])


class NicknameCommand(Bloxlink.Module):
    """manage the nickname users are given by Bloxlink"""

    def __init__(self):
        self.category = "Administration"
        self.permissions = Bloxlink.Permissions().build("BLOXLINK_MANAGER")
        self.arguments = [
            {
                "prompt": "Bloxlink supports advanced nicknaming of users. I'll show you "
                          "the different types of nicknames and how to change them.\n\n"
                          f"`Bind Nickname` {ARROW} when you link groups, you're given the "
                          "option to change nicknames of group members. Bloxlink will choose the "
                          "person's **highest role** which has an available Bind Nickname. Bind "
                          "Nicknames can be applied from `{prefix}bind`. If no bind nicknames "
                          "apply to the user, then the **Global Nickname** is used instead.\n"
                          f"`Global Nickname` {ARROW} the default nickname used if someone has **NO** "
                          "available Bind Nicknames. This can be applied from this command and "
                          "`{prefix}settings change` (look for \"Nickname Template\").",
                "name": "_",
                "type": "choice",
                "choices": ("next",),
                "footer": "Say **next** to change your Global Nickname."
            },
            {
                "prompt": "What would you like your Global Nickname to be? Remember, this nickname "
                          "will be used if someone has no available Bind Nickname from the `{prefix}bind` "
                          "command. You may combine templates. Templates: ```" + ESCAPED_NICKNAME_TEMPLATES + "```",
                "footer": "Say **skip** to leave this as the default nickname.",
                "name": "global_nickname"
            }
        ]

    async def __main__(self, CommandArgs):
        response = CommandArgs.response
        guild_data = CommandArgs.guild_data
        author = CommandArgs.author
        guild = CommandArgs.guild

        global_nickname = CommandArgs.parsed_args["global_nickname"]

        if "display-name" in global_nickname:
            display_name_confirm = (await CommandArgs.prompt([{
                "prompt": "**Warning!** You chose Display Names for your Nickname Template.\n"
                          "Display Names **aren't unique** and can **lead to impersonation.** Are you sure you want to use this? yes/no",
                "type": "choice",
                "choices": ("yes", "no"),
                "name": "confirm",
                "embed_title": "Display Names Confirmation",
                "embed_color": BROWN_COLOR,
                "formatting": False
            }]))["confirm"]

            if display_name_confirm == "no":
                raise CancelledPrompt

        if global_nickname.lower() != "skip":
            guild_data["nicknameTemplate"] = global_nickname

            await self.r.table("guilds").insert(guild_data, conflict="update").run()

            await post_event(guild, guild_data, "configuration", f"{author.mention} ({author.id}) has **changed** the `nicknameTemplate` option.", BROWN_COLOR)

            await set_guild_value(guild, "nicknameTemplate", global_nickname)

            await response.success("Successfully saved your new **Global Nickname!**")
        else:
            await response.info("No edits to your nickname were made.")
