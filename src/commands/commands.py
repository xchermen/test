from resources.structures import Bloxlink, InteractionPaginator # pylint: disable=import-error, no-name-in-module, no-name-in-module
from resources.exceptions import Error # pylint: disable=import-error, no-name-in-module, no-name-in-module
from resources.constants import ARROW, OWNER, HELP_DESCRIPTION # pylint: disable=import-error, no-name-in-module, no-name-in-module
import discord

get_enabled_addons = Bloxlink.get_module("addonsm", attrs=["get_enabled_addons"])
commands = Bloxlink.get_module("commands", attrs=["commands"])




@Bloxlink.command
class CommandsCommand(Bloxlink.Module):
    """view the command list, or get help on a certain command"""

    def __init__(self):
        self.aliases = ["cmds"]
        self.arguments = [
            {
                "prompt": "Please specify the command name",
                "optional": True,
                "name": "command_name"
            }
        ]
        self.dm_allowed = True
        self.slash_enabled = True

    async def __main__(self, CommandArgs):
        command_name = CommandArgs.parsed_args.get("command_name")
        prefix = CommandArgs.prefix
        response = CommandArgs.response
        guild = CommandArgs.guild
        author = CommandArgs.author

        if command_name:
            command_name = command_name.lower()

            for name, command in commands.items():
                if name == command_name or command_name in command.aliases:
                    embed = discord.Embed(title=f"{prefix}{name}", description=command.full_description or "N/A")
                    embed.set_author(name="Bloxlink", icon_url=Bloxlink.user.avatar.url)
                    embed.add_field(name="Category", value=command.category)

                    if command.usage:
                        embed.add_field(name="Usage", value=f"`{prefix}{name} {command.usage}`")
                    else:
                        embed.add_field(name="Usage", value=f"`{prefix}{name}`")

                    if command.aliases:
                        if len(command.aliases) > 1:
                            embed.add_field(name="Aliases", value=", ".join(command.aliases))
                        else:
                            embed.add_field(name="Alias", value=", ".join(command.aliases))

                    permissions = command.permissions
                    permission_text = []

                    if (permissions.premium or command.category == "Premium") and not command.free_to_use:
                        permission_text.append("**Premium Command**\nThis command can only be used by Bloxlink Premium members.")

                    if permissions.bloxlink_role:
                        if permissions.bloxlink_role == "Bloxlink Updater":
                            permission_text.append("**Bloxlink Updater**\nTo grant this permission:\n"
                                                   "You need a role called `Bloxlink Updater`, or "
                                                   "the `Manage Server` or `Manage Roles` role permission.")

                        elif permissions.bloxlink_role == "Bloxlink Moderator":
                            permission_text.append("**Bloxlink Moderator**\nTo grant this permission:\n"
                                                   "You need the `Kick Members` or `Ban Members` role permission.")

                        elif permissions.bloxlink_role == "Bloxlink Manager":
                            permission_text.append("**Bloxlink Manager**\nTo grant this permission:\n"
                                                   "You need the `Manage Server` role permission.")

                        elif permissions.bloxlink_role == "Bloxlink Admin":
                            permission_text.append("**Bloxlink Admin**\nTo grant this permission:\n"
                                                   "You need the `Administrator` role permission.")

                    if permissions.developer_only or command.category == "Developer":
                        permission_text.append("**Developer Only**\nThis command can only be used by the Bloxlink Developer.")

                    if permissions.allowed["roles"]:
                        permission_text.append("**Role Names**\nTo grant this permission:\n"
                                              f"You need the following role(s): `{', '.join(permissions.allowed['roles'])}`")

                    if permissions.allowed["functions"]:
                        permission_text.append("**Custom Permission**\nYou must meet a custom predicate to use this command.")

                    if permissions.allowed["discord_perms"]:
                        permission_text.append("**Discord Permission**\nYou must have the following role permission(s):"
                                               f"`{', '.join(permissions.allowoed['discord_perms'])}`")

                    if permission_text:
                        embed.add_field(name="Permissions", value="\n\n".join(permission_text))

                    if command.examples:
                        examples = []

                        for example in command.examples:
                            examples.append(f"{prefix}{command_name} {example}")

                        embed.add_field(name="Examples", value="\n".join(examples))

                    await response.send(embed=embed)

                    break
            else:
                raise Error(f"This command does not exist! Please use `{prefix}help` to view a full list of commands.")
        else:
            commands_categories = {}
            enabled_addons = guild and await get_enabled_addons(guild) or {}

            for command_name, command in commands.items():
                if (command.hidden or (command.addon and str(command.addon) not in enabled_addons)) and author.id != OWNER:
                    continue

                commands_categories[command.category] = commands_categories.get(command.category) or []
                commands_categories[command.category].append(f"**[{prefix}{command_name}](https://blox.link/commands/{command_name})**\n<:Reply:872019019677450240>{command.description}")


            paginator = InteractionPaginator(commands_categories, response, max_items=8, use_fields=False, default_category="Miscellaneous", description="Roblox Verification made easy! Features everything you need to integrate your Discord server with Roblox.")

            await paginator()
