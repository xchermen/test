from resources.structures.Bloxlink import Bloxlink  # pylint: disable=import-error, no-name-in-module
from resources.exceptions import Message  # pylint: disable=import-error, no-name-in-module
from resources.constants import ARROW, BROWN_COLOR # pylint: disable=import-error, no-name-in-module
import discord


post_event = Bloxlink.get_module("utils", attrs=["post_event"])
get_features = Bloxlink.get_module("premium", attrs=["get_features"])
set_guild_value = Bloxlink.get_module("cache", attrs=["set_guild_value"])


@Bloxlink.command
class LogChannelCommand(Bloxlink.Module):
    """subscribe to certain Bloxlink events. these will be posted in your channel(s)."""

    def __init__(self):
        self.arguments = [
            {
                "prompt": "Would you like to **change** your log channels (add/delete), or **view** your "
                          "current log channels?",
                "name": "choice",
                "type": "choice",
                "components": [discord.ui.Select(max_values=1, options=[
                        discord.SelectOption(label="Change log channels", description="Add/delete a log channel."),
                        discord.SelectOption(label="View log channels", description="View your log channels.")
                    ])],
                "choices": ["change log channels", "add", "delete", "view log channels"]
            }
        ]

        self.permissions = Bloxlink.Permissions().build("BLOXLINK_MANAGER")
        self.category = "Administration"
        self.aliases = ["logchannels", "log-channel", "log-channels"]
        self.slash_enabled = True

    async def __main__(self, CommandArgs):
        choice = CommandArgs.parsed_args["choice"][0]

        if choice in ("change log channels", "add", "change", "delete"):
            return await self.change(CommandArgs)
        else:
            return await self.view(CommandArgs)

    @Bloxlink.subcommand()
    async def change(self, CommandArgs):
        """add/delete a log channel"""

        prefix = CommandArgs.prefix
        response = CommandArgs.response
        guild_data = CommandArgs.guild_data

        author = CommandArgs.author
        guild = CommandArgs.guild

        log_channels = guild_data.get("logChannels") or {}

        parsed_args = await CommandArgs.prompt([
            {
                "prompt": "Please select an **event** to add/delete:\n"
                          "`all` "              + ARROW + " all events will be sent to your channel\n"
                          "`verifications` "    + ARROW + " user verifications will be logged "
                                                            "to your channel\n"
                          "`configurations` "   + ARROW + " any Bloxlink setting alteration will be "
                                                            "logged to your channel\n"
                         "`inactivity notices` _(premium)_ " + ARROW + " user-set inactivity notices "
                                                                         "from `" + prefix + "profie` will "
                                                                         "be logged to your channel\n"
                        "`binds` "              + ARROW +   " bind insertions/deletions will be logged to your channel\n"
                        "`moderation` "         + ARROW +   " automatic moderation actions by certain features will be "
                                                              "logged to your channel",

                "name": "log_type",
                "type": "choice",
                "components": [discord.ui.Select(max_values=1, options=[
                        discord.SelectOption(label="All events", description="Subscribe to all event types."),
                        discord.SelectOption(label="Verification Events", description="Fired when someome verifies."),
                        discord.SelectOption(label="Configuration Events", description="Fired when a setting is changed."),
                        discord.SelectOption(label="Inactivity Notice Events", description="Fired when someone from your server goes inactive."),
                        discord.SelectOption(label="Bind Events", description="Fired when someone binds a role."),
                        discord.SelectOption(label="Moderation Events", description="Fired when Bloxlink moderates someone.")
                    ])],
                "choices": ["all events", "verification events", "configuration events", "inactivity notice events", "bind events", "moderation events"]
            },
            {
                "prompt": "Please either **mention a channel**, or say a **channel name.**\n"
                          "Successful `{log_type[0]}` will be posted to this channel.\n\n"
                          "**Please make sure Bloxlink has permission to send/read messages "
                          "from the channel!**",
                "name": "log_channel",
                "footer": "Say **clear** to **delete** an already existing log channel of this type.",
                "type": "channel",
                "exceptions": ["clear", "delete"]
            }
        ], last=True)

        log_type = {
            "all events": "all",
            "verification events": "verifications",
            "configuration events": "configurations",
            "inactivity notice events": "inactivity notices",
            "bind events": "binds",
            "moderation events": "moderation"
        }[parsed_args["log_type"][0]]

        if log_type.endswith("s"):
            log_type = log_type[:-1] # remove ending "s" - looks better on embed titles

        log_channel = parsed_args["log_channel"]
        action = None

        if log_type == "inactivity events":
            donator_profile, _ = await get_features(discord.Object(id=guild.owner_id), guild=guild)

            if not donator_profile.features.get("premium"):
                raise Message("Only premium subscribers can subscribe to `inactivity notices`!\n"
                              f"Please use `{prefix}donate` for instructions on subscribing to premium.", type="info")

        if log_channel in ("clear", "delete"):
            log_channels.pop(log_type, None)
            action = "deleted"
        else:
            log_channels[log_type] = str(log_channel.id)
            action = "saved"

        if not log_channels:
            guild_data.pop("logChannels", None)
        else:
            guild_data["logChannels"] = log_channels


        await self.r.table("guilds").insert(guild_data, conflict="replace").run()

        await set_guild_value(guild, "logChannels", log_channels)

        await post_event(guild, guild_data, "configuration", f"{author.mention} ({author.id}) has **changed** the `log channels`.", BROWN_COLOR)

        await response.success(f"Successfully **{action}** your log channel!")


    @Bloxlink.subcommand()
    async def view(self, CommandArgs):
        """view your log channels"""

        guild = CommandArgs.guild
        guild_data = CommandArgs.guild_data

        log_channels = guild_data.get("logChannels") or {}

        response = CommandArgs.response

        if not log_channels:
            raise Message("You have no log channels!", type="confused")

        embed = discord.Embed(title="Bloxlink Log Channels")
        embed.set_footer(text="Powered by Bloxlink", icon_url=Bloxlink.user.avatar.url)
        embed.set_author(name=guild.name, icon_url=guild.icon.url if guild.icon else "")

        description = []

        for log_type, log_channel_id in log_channels.items():
            log_channel = guild.get_channel(int(log_channel_id))
            description.append(f"`{log_type}` {ARROW} {log_channel and log_channel.mention or '(Deleted)'}")

        embed.description = "\n".join(description)

        await response.send(embed=embed)
