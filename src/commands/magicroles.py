from resources.structures.Bloxlink import Bloxlink # pylint: disable=import-error, no-name-in-module, no-name-in-module
from resources.constants import ARROW, BROWN_COLOR, MAGIC_ROLES # pylint: disable=import-error, no-name-in-module, no-name-in-module
from resources.exceptions import Error # pylint: disable=import-error, no-name-in-module, no-name-in-module
import discord


post_event = Bloxlink.get_module("utils", attrs=["post_event"])
set_guild_value = Bloxlink.get_module("cache", attrs=["set_guild_value"])
get_features = Bloxlink.get_module("premium", attrs=["get_features"])


@Bloxlink.command
class MagicRolesCommand(Bloxlink.Module):
    """add/view/remove magic roles"""

    def __init__(self):
        self.permissions = Bloxlink.Permissions().build("BLOXLINK_MANAGER")
        self.category = "Premium"
        self.arguments = [{
            "prompt": "Magic Roles allow you to create roles that have special abilities within Bloxlink.\n\n"
                      "Would you like to **add** a new magic role, **view** your existing magic roles, or "
                      "**delete** an existing magic role?",
            "type": "choice",
            "components": [discord.ui.Select(max_values=1, options=[
                    discord.SelectOption(label="Add a new Magic Role"),
                    discord.SelectOption(label="View Magic Roles"),
                    discord.SelectOption(label="Delete a Magic Role"),
                ])],
            "choices": ("add a new magic role", "view magic roles", "delete a magic role"),
            "name": "subcommand"
        }]
        self.hidden = True
        self.aliases = ["magicrole", "magicroles", "magic-roles"]
        self.free_to_use = True

    async def __main__(self, CommandArgs):
        subcommand = CommandArgs.parsed_args["subcommand"][0]

        if subcommand == "add a new magic role":
            await self.add(CommandArgs)
        elif subcommand == "view magic roles":
            await self.view(CommandArgs)
        elif subcommand == "delete a magic role":
            await self.delete(CommandArgs)

    @Bloxlink.subcommand()
    async def add(self, CommandArgs):
        """add a new Magic Role to Bloxlink"""

        guild_data = CommandArgs.guild_data
        guild      = CommandArgs.guild
        response   = CommandArgs.response
        author     = CommandArgs.author
        prefix     = CommandArgs.prefix

        premium_status, _ = await get_features(discord.Object(id=guild.owner_id), guild=guild)

        if not premium_status.features.get("premium"):
            magic_roles_desc = "\n".join([f'**{x}** {ARROW} {y}' for x,y in MAGIC_ROLES.items()])
            raise Error("Customizing Magic Roles is reserved for __Bloxlink Premium subscribers!__ You may find out "
                        f"more information with the `{prefix}donate` command.\n\n"
                        "However, you may manually create a Bloxlink Magic Role "
                        f"and assign it one of these names, then give it to people!\n{magic_roles_desc}")

        parsed_args = await CommandArgs.prompt([
            {
                "prompt": "Which `role` would you like to use for this Magic Role?",
                "name": "role",
                "type": "role"
            },
            {
                "prompt": "Now the fun part! Let's choose what this Magic Role can do :sparkles:.\n\n"
                          "Please select the features this Magic Role can do.",
                "name": "features",
                "components": [discord.ui.Select(max_values=len(MAGIC_ROLES), options=[
                                discord.SelectOption(label=k, description=v)
                                for k,v in MAGIC_ROLES.items()
                ])],
                "type": "choice",
                "choices": ("Bloxlink Bypass", "Bloxlink Updater", "Bloxlink Admin")
            }
        ])

        role = parsed_args["role"]
        features = parsed_args["features"]

        magic_roles = guild_data.get("magicRoles", {})

        magic_roles[str(role.id)] = features
        guild_data["magicRoles"] = magic_roles

        await self.r.table("guilds").insert(guild_data, conflict="update").run()
        await set_guild_value(guild, "magicRoles", magic_roles)
        await post_event(guild, guild_data, "configuration", f"{author.mention} ({author.id}) has **added** a new `magicRole`!", BROWN_COLOR)

        await response.success("Successfully **saved** your new Magic Role! Go assign it to some people! :sparkles:")

    @Bloxlink.subcommand()
    async def view(self, CommandArgs):
        """view your Magic Roles in your server"""

        guild_data = CommandArgs.guild_data
        magic_roles = guild_data.get("magicRoles", {})
        guild = CommandArgs.guild
        response = CommandArgs.response
        embed = discord.Embed(title="Bloxlink Magic Roles", description="Magic Roles allow you to customize the "
                              "permissions of individual users by giving them a role.")

        magic_role_sorted = {}
        has_magic_role = False

        for role in guild.roles:
            if role.name in MAGIC_ROLES:
                magic_role_sorted[role.name] = {role.mention}
                has_magic_role = True

        if magic_roles:
            has_magic_role = True

        for magic_role_id, magic_role_features in magic_roles.items():
            role = guild.get_role(int(magic_role_id))

            for feature in magic_role_features:
                magic_role_sorted[feature] = magic_role_sorted.get(feature) or set()

                if role:
                    magic_role_sorted[feature].add(role.mention)
                else:
                    magic_role_sorted[feature].add(f"Deleted role: {magic_role_id}")

        for magic_role_name, roles in magic_role_sorted.items():
            embed.add_field(name=magic_role_name, value=f"**Description** {ARROW} {MAGIC_ROLES[magic_role_name]}\n**Roles** {ARROW} " + ", ".join(roles), inline=False)

        if has_magic_role:
            await response.send(embed=embed)
        else:
            await response.silly("There are no Magic Roles to display!")

    @Bloxlink.subcommand()
    async def delete(self, CommandArgs):
        """delete a Magic Role from your server"""

        response = CommandArgs.response
        guild    = CommandArgs.guild
        author   = CommandArgs.author

        guild_data  = CommandArgs.guild_data
        magic_roles = guild_data.get("magicRoles", {})

        if not (magic_roles or discord.utils.find(lambda r: r.name in MAGIC_ROLES, guild.roles)):
            await response.silly("You have no Magic Roles!")
            return

        parsed_args = await CommandArgs.prompt([
            {
                "prompt": "Which `role` are you trying to remove? Please either say the role name or ping it.",
                "name": "role",
                "type": "role"
            }
        ])

        role = parsed_args["role"]
        magic_role = magic_roles.get(str(role.id))
        removed_builtin_magic_role = False
        builtin_magic_role = False

        if role.name in MAGIC_ROLES:
            builtin_magic_role = True

            try:
                await role.delete()
            except discord.errors.Forbidden:
                await response.error("I don't have permission to remove this Magic Role! Please give me the `Manage Roles` permission.")
            else:
                await response.success("Successfully **removed** this Magic Role!")
                removed_builtin_magic_role = True

        if not (magic_role or builtin_magic_role):
            await response.silly("This is not a Magic Role!")
        else:
            if magic_role:
                magic_roles.pop(str(role.id))

                if magic_roles:
                    guild_data["magicRoles"] = magic_roles
                else:
                    guild_data.pop("magicRoles")

                await self.r.table("guilds").insert(guild_data, conflict="replace").run()
                await set_guild_value(guild, "magicRoles", magic_roles)

            await post_event(guild, guild_data, "configuration", f"{author.mention} ({author.id}) has **removed** a `magicRole`!", BROWN_COLOR)

            if not removed_builtin_magic_role:
                await response.success("Successfully **removed** this Magic Role!")
