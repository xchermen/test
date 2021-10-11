from resources.structures.Bloxlink import Bloxlink # pylint: disable=import-error, no-name-in-module, no-name-in-module
from resources.constants import SERVER_VERIFIED_TEMPLATES, UNVERIFIED_TEMPLATES, BROWN_COLOR # pylint: disable=import-error, no-name-in-module, no-name-in-module
from resources.exceptions import Message # pylint: disable=import-error, no-name-in-module, no-name-in-module
import discord


post_event = Bloxlink.get_module("utils", attrs=["post_event"])
set_guild_value = Bloxlink.get_module("cache", attrs=["set_guild_value"])


@Bloxlink.command
class JoinChannelCommand(Bloxlink.Module):
    """greets people who join the server in your channel."""

    def __init__(self):
        self.permissions = Bloxlink.Permissions().build("BLOXLINK_MANAGER")
        self.category = "Administration"
        self.arguments = [{
            "prompt": "Would you like to alter/disable the join messages for **verified** or **unverified** users?",
            "type": "choice",
            "components": [discord.ui.Select(max_values=1, options=[
                           discord.SelectOption(label="Verified users", description="Change the message for verified users."),
                           discord.SelectOption(label="Unverified users", description="Change the message for unverified users."),
            ])],
            "choices": ("Verified users", "Unverified users"),
            "name": "subcommand"
        }]
        self.hidden = True
        self.aliases = ["join-channel"]

    async def __main__(self, CommandArgs):
        subcommand = CommandArgs.parsed_args["subcommand"][0]

        if subcommand == "Verified users":
            await self.verified(CommandArgs)
        elif subcommand == "Unverified users":
            await self.unverified(CommandArgs)

    @Bloxlink.subcommand()
    async def verified(self, CommandArgs):
        """set the join message of people who are VERIFIED on Bloxlink"""

        guild_data = CommandArgs.guild_data
        join_channel = guild_data.get("joinChannel") or {}
        verified_message = join_channel.get("verified")

        author = CommandArgs.author
        guild = CommandArgs.guild

        response = CommandArgs.response

        if verified_message:
            response.delete(await response.send("When people join your server and are **VERIFIED** on Bloxlink, this message "
                                                "will be posted:"))
            response.delete(await response.send(f"```{verified_message['message']}```"))

        parsed_args_1 = (await CommandArgs.prompt([{
            "prompt": "Would you like to **change** the message people get when they join and are verified, or "
                        "would you like to **disable** this feature?",
            "name": "option",
            "type": "choice",
            "components": [discord.ui.Select(max_values=1, options=[
                           discord.SelectOption(label="Change message", description="Change the message for verified users."),
                           discord.SelectOption(label="Disable", description="No join message for verified users."),
            ])],
            "choices": ("Change message", "Disable")
        }]))["option"][0]

        if parsed_args_1 == "Change message":
            parsed_args_2 = await CommandArgs.prompt([
                {
                    "prompt": "What would you like the text of the Verified Join Message to be? You may use "
                             f"these templates: ```{SERVER_VERIFIED_TEMPLATES}```",
                    "name": "text",
                    "max": 1500,
                    "formatting": False
                },
                {
                    "prompt": "Which **channel** would you like the join messages to be posted in?",
                    "name": "channel",
                    "type": "channel"
                },
                {
                    "prompt": "Let's customize the join message!",
                    "name": "features",
                    "type": "choice",
                    "components": [discord.ui.Select(max_values=4, options=[
                                   discord.SelectOption(label="Ping people", description="The embed will ping people."),
                                   discord.SelectOption(label="Include Roblox avatar", description="The embed will show the user's Roblox avatar."),
                                   discord.SelectOption(label="Include Roblox age", description="The embed will show the user's Roblox age."),
                                   discord.SelectOption(label="Include Roblox username", description="The embed will show the user's Roblox username."),
                                   discord.SelectOption(label="None of the above", description="There will be no embed."),
                    ])],
                    "choices": ("Include Roblox avatar", "Ping people", "Include Roblox age", "Include Roblox username", "None of the above")
                }
            ], last=True)

            channel = parsed_args_2["channel"]
            text    = parsed_args_2["text"]
            features = parsed_args_2["features"]
            includes = {}

            if "None of the above" not in features:
                for feature in features:
                    if feature == "Ping people":
                        includes["ping"] = True
                    elif feature == "Include Roblox avatar":
                        includes["robloxAvatar"] = True
                    elif feature == "Include Roblox age":
                        includes["robloxAge"] = True
                    elif feature == "Include Roblox username":
                        includes["robloxUsername"] = True

            join_channel["verified"] = {"channel": str(channel.id), "message": text, "includes": includes}
            guild_data["joinChannel"] = join_channel

            await set_guild_value(guild, "joinChannel", join_channel)

            await self.r.table("guilds").insert(guild_data, conflict="replace").run()

        elif parsed_args_1 == "Disable":
            join_channel.pop("verified", None)
            guild_data["joinChannel"] = join_channel

            await set_guild_value(guild, "joinChannel", join_channel)

            await self.r.table("guilds").insert(guild_data, conflict="replace").run()

        change_text = f"**{'changed' if parsed_args_1 == 'Change message' else 'disabled'}**"

        await post_event(guild, guild_data, "configuration", f"{author.mention} ({author.id}) has {change_text} the `joinChannel` option for `verified` members.", BROWN_COLOR)

        raise Message(f"Successfully {change_text} your join message.", type="success")

    @Bloxlink.subcommand()
    async def unverified(self, CommandArgs):
        """set the join message of people who are UNVERIFIED on Bloxlink"""

        guild_data = CommandArgs.guild_data
        join_channel = guild_data.get("joinChannel") or {}
        unverified_message = join_channel.get("unverified")

        author = CommandArgs.author
        guild = CommandArgs.guild

        response = CommandArgs.response

        if unverified_message:
            response.delete(await response.send("When people join your server and are **UNVERIFIED** on Bloxlink, this message "
                                                "will be posted:"))
            response.delete(await response.send(f"```{unverified_message['message']}```"))

        parsed_args_1 = (await CommandArgs.prompt([{
            "prompt": "Would you like to **change** the message people get when they join and are unverified, or "
                        "would you like to **disable** this feature?",
            "name": "option",
            "type": "choice",
            "components": [discord.ui.Select(max_values=1, options=[
                           discord.SelectOption(label="Change message", description="Change the message for unverified users."),
                           discord.SelectOption(label="Disable", description="No join message for unverified users."),
            ])],
            "choices": ("Change message", "Disable")
        }]))["option"][0]

        if parsed_args_1 == "Change message":
            parsed_args_2 = await CommandArgs.prompt([
                {
                    "prompt": "What would you like the text of the Unverified Join Message to be? You may use "
                             f"these templates: ```{UNVERIFIED_TEMPLATES}```",
                    "name": "text",
                    "max": 1500,
                    "formatting": False
                },
                {
                    "prompt": "Which **channel** would you like the join messages to be posted in?",
                    "name": "channel",
                    "type": "channel"
                },
                {
                    "prompt": "Would you like to keep the join messages in an embed format, or keep it as text?\nIt's "
                              "recommended to say `embed` if you chose to include avatars for the `verified` message "
                              "so the verified and unverified join messages look similar.",
                    "components": [discord.ui.Select(max_values=1, options=[
                                   discord.SelectOption(label="Use embed format", description="The join message will be in an embed."),
                                   discord.SelectOption(label="Use text format", description="The join message will be in a standard message."),
                    ])],
                    "name": "type",
                    "type": "choice",
                    "choices": ("Use embed format", "Use text format")
                }
            ], last=True)

            channel = parsed_args_2["channel"]
            text    = parsed_args_2["text"]
            embed_format = parsed_args_2["type"][0] == "Use embed format"
            includes = {}

            parsed_args_3 = await CommandArgs.prompt([
                {
                    "prompt": "Would you like this join message to ping people?",
                    "name": "ping",
                    "type": "choice",
                    "components": [discord.ui.Select(max_values=1, options=[
                                   discord.SelectOption(label="Ping people", description="The message will ping people."),
                                   discord.SelectOption(label="Don't ping people", description="The message will NOT ping anyone."),
                    ])],
                    "choices": ("Ping people", "Don't ping people")
                },
            ], last=True)

            if parsed_args_3["ping"][0] == "Ping people":
                includes["ping"] = True

            join_channel["unverified"] = {"channel": str(channel.id), "message": text, "includes": includes, "embed": embed_format}
            guild_data["joinChannel"] = join_channel

            await set_guild_value(guild, "joinChannel", join_channel)

            await self.r.table("guilds").insert(guild_data, conflict="replace").run()

        else:
            join_channel.pop("unverified", None)
            guild_data["joinChannel"] = join_channel

            await set_guild_value(guild, "joinChannel", join_channel)

            await self.r.table("guilds").insert(guild_data, conflict="replace").run()

        change_text = f"**{'changed' if parsed_args_1 == 'Change message' else 'disabled'}**"

        await post_event(guild, guild_data, "configuration", f"{author.mention} ({author.id}) has {change_text} the `joinChannel` option for `verified` members.", BROWN_COLOR)

        raise Message(f"Successfully {change_text} your join message.", type="success")
