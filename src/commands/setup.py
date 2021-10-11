from resources.structures.Bloxlink import Bloxlink # pylint: disable=import-error, no-name-in-module
from resources.constants import ARROW, BROWN_COLOR, NICKNAME_TEMPLATES, TRELLO # pylint: disable=import-error, no-name-in-module
from resources.exceptions import Error, RobloxNotFound, CancelCommand # pylint: disable=import-error, no-name-in-module
from aiotrello.exceptions import TrelloNotFound, TrelloUnauthorized, TrelloBadRequest
import discord
import re

NICKNAME_DEFAULT = "{smart-name}"
VERIFIED_DEFAULT = "Verified"

get_group = Bloxlink.get_module("roblox", attrs=["get_group"])
trello, get_options = Bloxlink.get_module("trello", attrs=["trello", "get_options"])
post_event = Bloxlink.get_module("utils", attrs=["post_event"])
clear_guild_data = Bloxlink.get_module("cache", attrs=["clear_guild_data"])

roblox_group_regex = re.compile(r"roblox.com/groups/(\d+)/")


@Bloxlink.command
class SetupCommand(Bloxlink.Module):
    """set-up your server with Bloxlink"""

    def __init__(self):
        self.permissions = Bloxlink.Permissions().build("BLOXLINK_MANAGER")
        self.category = "Administration"
        self.aliases = ["set-up"]
        self.slash_enabled = True

    @staticmethod
    async def validate_group(message, content, prompt, guild):
        if content.lower() in ("skip", "next"):
            return "skip"

        regex_search = roblox_group_regex.search(content)

        if regex_search:
            group_id = regex_search.group(1)
        else:
            group_id = content

        try:
            group = await get_group(group_id, full_group=True)
        except RobloxNotFound:
            return None, "No group was found with this ID. Please try again."

        return group

    @staticmethod
    async def validate_trello_board(message, content, prompt, guild):
        content_lower = content.lower()

        if content_lower in ("skip", "next"):
            return "skip"
        elif content_lower == "disable":
            return "disable"

        try:
            board = await trello.get_board(content, card_limit=TRELLO["CARD_LIMIT"], list_limit=TRELLO["LIST_LIMIT"])
        except (TrelloNotFound, TrelloBadRequest):
            return None, "No Trello board was found with this ID. Please try again."
        except TrelloUnauthorized:
            return None, "I don't have permission to view this Trello board; please make sure " \
                         "this Trello board is set to **PUBLIC**, or add `@bloxlink` to your Trello board."

        return board

    async def __main__(self, CommandArgs):
        guild = CommandArgs.guild
        author = CommandArgs.author
        response = CommandArgs.response
        prefix = CommandArgs.prefix

        guild_data = CommandArgs.guild_data
        group_ids = guild_data.get("groupIDs", {})

        settings_buffer = []

        parsed_args_1 = {}
        parsed_args_2 = {}
        parsed_args_3 = {}
        parsed_args_4 = {}

        nickname = None

        response.delete(await response.info("See this video for a set-up walkthrough: <https://blox.link/tutorial/setup/>", dm=False, no_dm_post=True))

        parsed_args_1 = await CommandArgs.prompt([
            {
                "prompt": "**Thank you for choosing Bloxlink!** In a few simple prompts, **we'll configure Bloxlink for your server.**\n\n"
                          "**Pre-configuration:**\nBefore continuing, please ensure that Bloxlink has all the proper permissions, "
                          "such as the ability to `manage roles, nicknames, channels`, etc. If you do not set these "
                          "permissions, you may encounter issues with using certain commands.",
                "name": "_",
                "footer": "Say **next** to continue.",
                "type": "choice",
                "choices": ["next"],
                "components": [discord.ui.Button(label="Next", style=discord.ButtonStyle.primary)],
                "embed_title": "Setup Prompt"
            },
            {
                "prompt": "Should your members be given a nickname? Please create a nickname using these templates. You may "
                          f"combine templates. The templates MUST match exactly.\n\n**Templates:** ```{NICKNAME_TEMPLATES}```",
                "name": "nickname",
                "embed_title": "Setup Prompt",
                "footer": "Say **disable** to not have a nickname.\nSay **skip** to leave this as the default (`{smart-name}`).",
                "formatting": False,
                "exceptions": ("disable", "skip")
            },
            {
                "prompt": "Would you like to change the **Verified role** (the role people are given if they're linked to Bloxlink) name to something else?\n"
                          "Default: `Verified`",
                "name": "verified_role",
                "footer": "Say **disable** to disable the Verified role.\nSay **skip** to leave as-is.",
                "embed_title": "Setup Prompt",
                "max": 50
            },
            {
                "prompt": "Would you like to link a **Roblox group** to this Discord server? Please provide the **Group URL, or Group ID**.",
                "name": "group",
                "footer": "Say **skip** to leave as-is.",
                "embed_title": "Setup Prompt",
                "validation": self.validate_group
            }
        ], dm=False, no_dm_post=False)

        for k, v in parsed_args_1.items():
            if k != "_":
                settings_buffer.append(f"**{k}** {ARROW} {v}")

        group = parsed_args_1["group"]
        verified = parsed_args_1["verified_role"]
        nickname = parsed_args_1["nickname"] if parsed_args_1["nickname"] != "disable" else "{disable-nicknaming}"
        verified_lower = verified.lower()

        if group not in ("next", "skip"):
            group_ids[group.group_id] = {"nickname": None, "groupName": group.name}

            merge_replace = (await CommandArgs.prompt([
                {
                    "prompt": "Would you like to automatically transfer your Roblox group ranks to Discord roles?\nValid choices:\n"
                              "`merge` — This will **NOT** remove any roles. Your group Rolesets will be **merged** with your current roles.\n"
                              "`replace` — **This will REMOVE and REPLACE your CURRENT ROLES** with your Roblox group Rolesets. You'll "
                              "need to configure permissions and colors yourself.\n"
                              "`skip` — nothing will be changed.",
                    "name": "merge_replace",
                    "type": "choice",
                    "components": [discord.ui.Select(max_values=1, options=[
                            discord.SelectOption(label="Merge", description="No roles will be removed, only added."),
                            discord.SelectOption(label="Replace", description="This will remove your existing roles."),
                            discord.SelectOption(label="Skip", description="Your roles will be un-touched.")
                        ])],
                    "choices": ["merge", "replace", "skip", "next"],
                    "embed_title": "Setup Prompt"

                }
            ], dm=False, no_dm_post=True))["merge_replace"][0]

            if merge_replace  == "next":
                merge_replace = "skip"

            group_ids[group.group_id] = {"nickname": None, "groupName": group.name}

            settings_buffer.append(f"**merge_replace** {ARROW} {merge_replace}")

        if CommandArgs.trello_board:
            parsed_args_3 = (await CommandArgs.prompt([
                {
                    "prompt": "We've detected that you have a **Trello board** linked to this server!\n"
                              "Trello functionality on Bloxlink is **deprecated** and **will be removed** "
                              "in a future update in favor of our upcoming **Server Dashboard**.\n\n"
                              "You may unlink Trello from your server by saying `disable`.\nIf you're "
                              "not ready to unlink Trello yet, say `skip`.",
                    "name": "trello_choice",
                    "type": "choice",
                    "components": [discord.ui.Select(max_values=1, options=[
                            discord.SelectOption(label="Disable", description="Your Trello board will be unlinked."),
                            discord.SelectOption(label="Skip")
                        ])],
                    "choices": ["disable", "skip"],
                    "embed_title": "Trello Deprecation"

                }
            ], dm=False, no_dm_post=True))["trello_choice"]

            if parsed_args_3[0] == "disable":
                guild_data.pop("trelloID")


        parsed_args_4 = await CommandArgs.prompt([
            {
                "prompt": "You have reached the end of the setup. Here are your current settings:\n"
                           + "\n".join(settings_buffer),
                "name": "setup_complete",
                "type": "choice",
                "footer": "Please say **done** to complete the setup.",
                "choices": ["done"],
                "embed_title": "Setup Prompt Confirmation",
                "embed_color": BROWN_COLOR,
                "components": [discord.ui.Button(label="Done", style=discord.ButtonStyle.primary)],
                "formatting": False
            }
        ], dm=False, no_dm_post=True, last=True)

        if group and group != "skip":
            if merge_replace not in ("skip", "next"):
                if merge_replace == "replace":
                    for role in list(guild.roles):
                        try:
                            if not (role in guild.me.roles or role.is_default()):
                                try:
                                    await role.delete(reason=f"{author} chose to replace roles through {prefix}setup")
                                except discord.errors.Forbidden:
                                    pass
                                except discord.errors.HTTPException:
                                    pass

                        except AttributeError: # guild.me is None -- bot kicked out
                            raise CancelCommand

                for _, roleset_data in group.rolesets.items():
                    if not discord.utils.find(lambda r: r.name == roleset_data[0], guild.roles):
                        try:
                            await guild.create_role(name=roleset_data[0])
                        except discord.errors.Forbidden:
                            raise Error("Please ensure I have the `Manage Roles` permission; setup aborted.")

        if verified:
            if verified_lower == "disable":
                guild_data["verifiedRoleEnabled"] = False
            elif verified_lower not in ("next", "skip"):
                guild_data["verifiedRoleName"] = verified
                guild_data["verifiedRoleEnabled"] = True

        if group_ids:
            guild_data["groupIDs"] = group_ids

        if nickname not in ("skip", "next"):
            guild_data["nicknameTemplate"] = nickname


        await self.r.table("guilds").insert(guild_data, conflict="replace").run()

        await post_event(guild, guild_data, "configuration", f"{author.mention} ({author.id}) has **set-up** the server.", BROWN_COLOR)

        await clear_guild_data(guild)

        await response.success("Your server is now **configured** with Bloxlink!", dm=False, no_dm_post=True)
