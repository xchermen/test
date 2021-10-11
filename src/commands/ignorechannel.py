from resources.structures.Bloxlink import Bloxlink # pylint: disable=import-error, no-name-in-module
from resources.constants import BROWN_COLOR # pylint: disable=import-error, no-name-in-module
from config import REACTIONS # pylint: disable=import-error, no-name-in-module
from resources.exceptions import CancelCommand # pylint: disable=import-error, no-name-in-module
import discord

post_event = Bloxlink.get_module("utils", attrs=["post_event"])
set_guild_value = Bloxlink.get_module("cache", attrs=["set_guild_value"])



@Bloxlink.command
class IgnoreChannelCommand(Bloxlink.Module):
    """enable/disable commands from a channel"""

    def __init__(self):
        self.permissions = Bloxlink.Permissions().build("BLOXLINK_MANAGER")
        self.category = "Administration"
        self.aliases = ["ignore", "ignore-channel"]
        self.slash_enabled = True
        self.slash_only = True

    async def __main__(self, CommandArgs):
        pass

    @Bloxlink.subcommand(arguments=[
        {
            "prompt": "Choose a channel to enable/disable commands from.",
            "name": "channel",
            "type": "channel",
            "create_missing_channel": False,
            "allow_categories": True,
            "optional": True
        },
        {
            "prompt": "Should any role be allowed to use commands?",
            "name": "bypass_role",
            "type": "role",
            "optional": True
        }
    ])
    async def toggle(self, CommandArgs):
        """enable/disable commands from a channel"""

        channel    = CommandArgs.parsed_args["channel"] or CommandArgs.channel
        channel_id = str(channel.id)

        bypass_role = CommandArgs.parsed_args["bypass_role"]

        guild  = CommandArgs.guild
        author = CommandArgs.author

        response   = CommandArgs.response
        guild_data = CommandArgs.guild_data

        ignored_channels = guild_data.get("ignoredChannels", {})
        current_entry    = ignored_channels.get(channel_id, {})
        bypass_roles     = current_entry.get("bypassRoles", [])
        current_status   = bool(current_entry)

        toggle_text = ""

        if bypass_role:
            if str(bypass_role.id) not in bypass_roles:
                bypass_roles.append(str(bypass_role.id))
                current_status = True
            else:
                # ask for update
                toggle_text = "enable commands" if current_status else "disable commands"

                confirm_update = (await CommandArgs.prompt([{
                    "prompt": "This role is already a bypass role! Would you like to "
                              f"instead **{toggle_text}** from this channel?",

                    "formatting": False,
                    "name": "confirm_update"
                }]))["confirm_update"]

                if confirm_update == "yes":
                    current_status = not current_status
                else:
                    raise CancelCommand("No changes made.")
        else:
            # do opposite
            current_status = not current_status

        if current_status:
            ignored_channels[channel_id] = {"bypassRoles": bypass_roles}
        else:
            ignored_channels.pop(channel_id, None)

        guild_data["ignoredChannels"] = ignored_channels

        await self.r.table("guilds").insert(guild_data, conflict="replace").run()

        await set_guild_value(guild, "ignoredChannels", ignored_channels)

        if current_status:
            await response.success(f"Successfully **disabled** commands from {channel.mention} from non-admins.\n"
                                   "If you would like to grant a certain person access to use commands, give them a role called "
                                   "`Bloxlink Bypass`."
            )
            await post_event(guild, guild_data, "configuration", f"{author.mention} ({author.id}) has **disabled** all commands for channel {channel.mention}.", BROWN_COLOR)
        else:
            await response.success(f"Successfully **enabled** commands from {channel.mention}.")
            await post_event(guild, guild_data, "configuration", f"{author.mention} ({author.id}) has **enabled** all commands for channel {channel.mention}.", BROWN_COLOR)


    @Bloxlink.subcommand()
    async def view(self, CommandArgs):
        """view your channel configuration"""

        guild = CommandArgs.guild

        response   = CommandArgs.response
        guild_data = CommandArgs.guild_data

        desc = []

        embed = discord.Embed(title="Ignored Channels")
        embed.set_footer(text="Admins can still use commands in these channels or categories!")

        if guild_data.get("ignoredChannels"):
            ignored_channels = guild_data["ignoredChannels"]
            allowed_channels = [c for c in guild.text_channels if str(c.id) not in ignored_channels]

            for ignored_channel_id, ignored_channel_data in ignored_channels.items():
                channel_id = int(ignored_channel_id)
                category_channel = None
                text_channel = discord.utils.find(lambda c: c.id == channel_id, guild.text_channels)

                bypass_roles = ignored_channel_data["bypassRoles"]
                bypass_roles_buffer = []
                bypass_roles_text = ""

                if bypass_roles:
                    for bypass_role_id in bypass_roles:
                        bypass_role = discord.utils.find(lambda r: r.id == int(bypass_role_id), guild.roles)

                        if bypass_role:
                            bypass_roles_buffer.append(bypass_role.mention)
                        else:
                            bypass_roles_buffer.append(f"(Deleted Role: {bypass_role_id})")

                if bypass_roles_buffer:
                    bypass_roles_text = f"\n{REACTIONS['BLANK']}{REACTIONS['REPLY']} **Bypass Roles:** " + ", ".join(bypass_roles_buffer)

                if not text_channel:
                    category_channel = discord.utils.find(lambda c: c.id == channel_id, guild.categories)

                if text_channel or category_channel:
                    desc.append(
                        f"{REACTIONS['RED']} {'**Channel:** ' if text_channel else '**Category:** '} {text_channel.mention if text_channel else category_channel.name}{bypass_roles_text}"
                    )
                else:
                    desc.append(
                        f"{REACTIONS['RED']} **INVALID CHANNEL:** {channel_id}"
                    )

            if allowed_channels:
                for allowed_channel in allowed_channels[:10]:
                    desc.append(
                        f"{REACTIONS['GREEN']} **Channel:** {allowed_channel.mention}"
                    )

                len_remaining = len(allowed_channels[10:])

                if len_remaining:
                    desc.append(f"_And {len_remaining} more..._")

            embed.description = "\n".join(desc)

        if not desc:
            embed.description = "You have no ignored channels!"

        await response.send(embed=embed)
