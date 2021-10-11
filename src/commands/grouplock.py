from resources.structures.Bloxlink import Bloxlink  # pylint: disable=import-error, no-name-in-module
from resources.exceptions import RobloxNotFound, Message  # pylint: disable=import-error, no-name-in-module
from resources.constants import BROWN_COLOR # pylint: disable=import-error, no-name-in-module
from resources.exceptions import Error # pylint: disable=import-error, no-name-in-module
import re
import discord


post_event = Bloxlink.get_module("utils", attrs=["post_event"])
get_group = Bloxlink.get_module("roblox", attrs=["get_group"])
get_features = Bloxlink.get_module("premium", attrs=["get_features"])
set_guild_value = Bloxlink.get_module("cache", attrs="set_guild_value")

roblox_group_regex = re.compile(r"roblox.com/groups/(\d+)/")


@Bloxlink.command
class GroupLockCommand(Bloxlink.Module):
    """lock your server to group members"""


    @staticmethod
    async def validate_group(message, content, prompt, guild):
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

    def __init__(self):
        self.arguments = [
            {
                "prompt": "This command will kick people who join your server and aren't in these groups. They must be in __ALL__ of these groups.\n"
                          "Would you like to **add** a new group, **delete** a group, or **view** your current groups?",
                "name": "choice",
                "type": "choice",
                "components": [discord.ui.Select(max_values=1, options=[
                        discord.SelectOption(label="Add a new group", description="Add a new group to your group-lock."),
                        discord.SelectOption(label="Delete a group", description="Delete a group from your group-lock."),
                        discord.SelectOption(label="View groups", description="View your group-lock."),
                    ])],
                "choices": ["add a new group", "delete a group", "view groups"]
            }
        ]

        self.permissions = Bloxlink.Permissions().build("BLOXLINK_MANAGER")
        self.category = "Administration"
        self.aliases = ["group-lock", "serverlock", "server-lock"]
        self._range_search = re.compile(r"([0-9]+)\-([0-9]+)")

    async def __main__(self, CommandArgs):
        choice = CommandArgs.parsed_args["choice"][0]
        guild_data = CommandArgs.guild_data
        groups = CommandArgs.guild_data.get("groupLock", {})
        guild = CommandArgs.guild
        author = CommandArgs.author
        prefix = CommandArgs.prefix
        response = CommandArgs.response

        if choice == "add a new group":
            args = await CommandArgs.prompt([
                {
                    "prompt": "Please specify either the **Group ID** or **Group URL** that you would like "
                              "to set as a requirement for new joiners.",
                    "name": "group",
                    "validation": self.validate_group
                },
                {
                    "prompt": "Should only a **specific Roleset** be allowed to join your server? You may specify a Roleset name or ID. You may "
                              "provide them in a list, and you may negate the number to capture everyone catch everyone with the rank _and above_.\n"
                              "Example: `-10, 5, VIP` means people who are ranked 5, VIP, or if their roleset is greater than 10 can join your server.",
                    "name": "rolesets",
                    "footer": "Say **skip** to skip this option; if skipped, the roleset people have wouldn't matter, they'll be able to enter "
                              "your server as long as they're in your group.",
                    "type": "list",
                    "exceptions": ("skip",),
                    "max": 10,
                },
                {
                    "prompt": "Would you like people who are kicked to receive a custom DM? Please specify either `yes` or `no`.\n\n"
                              "Note that Unverified users will receive a different DM on instructions to linking to Bloxlink.",
                    "name": "dm_enabled",
                    "type": "choice",
                    "choices": ["yes", "no"]
                }
            ])

            group = args["group"]
            dm_enabled = args["dm_enabled"] == "yes"
            rolesets_raw = args["rolesets"] if args["rolesets"] != "skip" else None

            parsed_rolesets = []

            if rolesets_raw:
                for roleset in rolesets_raw:
                    if roleset.isdigit():
                        parsed_rolesets.append(int(roleset))
                    elif roleset[:1] == "-":
                        try:
                            roleset = int(roleset)
                        except ValueError:
                            pass
                        else:
                            parsed_rolesets.append(roleset)
                    else:
                        range_search = self._range_search.search(roleset)

                        if range_search:
                            num1, num2 = range_search.group(1), range_search.group(2)
                            parsed_rolesets.append([int(num1), int(num2)])
                        else:
                            # they specified a roleset name as a string

                            roleset_find = group.rolesets.get(roleset.lower())

                            if roleset_find:
                                parsed_rolesets.append(roleset_find[1])

                if not parsed_rolesets:
                    raise Error("Could not resolve any valid rolesets! Please make sure you're typing the Roleset name correctly.")

            if len(groups) >= 15:
                raise Message("15 groups is the max you can add to your group-lock! Please delete some before adding any more.", type="silly")

            profile, _ = await get_features(discord.Object(id=guild.owner_id), guild=guild)

            if len(groups) >= 3 and not profile.features.get("premium"):
                raise Message("If you would like to add more than **3** groups to your group-lock, then you need Bloxlink Premium.\n"
                              f"Please use `{prefix}donate` for instructions on receiving Bloxlink Premium.\n"
                              "Bloxlink Premium members may lock their server with up to **15** groups.", type="info")

            if dm_enabled:
                dm_message = (await CommandArgs.prompt([{
                    "prompt": "Please specify the text of the DM that people who are kicked will receive. A recommendation "
                              "is to provide your Group Link and any other instructions for them.",
                    "name": "dm_message",
                    "max": 1500
                }], last=True))["dm_message"]
            else:
                dm_message = None

            groups[group.group_id] = {"groupName": group.name, "dmMessage": dm_message, "roleSets": parsed_rolesets}

            await self.r.table("guilds").insert({
                "id": str(guild.id),
                "groupLock": groups
            }, conflict="update").run()

            await post_event(guild, guild_data, "configuration", f"{author.mention} ({author.id}) has **added** a group to the `server-lock`.", BROWN_COLOR)

            await set_guild_value(guild, "groupLock", groups)

            await response.success(f"Successfully added group **{group.name}** to your Server-Lock!")

        elif choice == "delete a group":
            group = (await CommandArgs.prompt([
                {
                    "prompt": "Please specify either the **Group URL** or **Group ID** to delete.",
                    "name": "group",
                    "validation": self.validate_group
                }
            ], last=True))["group"]

            if not groups.get(group.group_id):
                raise Message("This group isn't in your server-lock!")

            del groups[group.group_id]
            guild_data["groupLock"] = groups

            if groups:
                await self.r.table("guilds").insert(guild_data, conflict="replace").run()
            else:
                guild_data.pop("groupLock")

                await self.r.table("guilds").insert(guild_data, conflict="replace").run()

            await post_event(guild, guild_data, "configuration", f"{author.mention} ({author.id}) has **deleted** a group from the `server-lock`.", BROWN_COLOR)

            await set_guild_value(guild, "groupLock", groups)

            await response.success("Successfully **deleted** your group from the Server-Lock!")


        elif choice == "view groups":
            if not groups:
                raise Message("You have no groups added to your Server-Lock!", type="info")

            embed = discord.Embed(title="Bloxlink Server-Lock")
            embed.set_footer(text="Powered by Bloxlink", icon_url=Bloxlink.user.avatar.url)
            embed.set_author(name=guild.name, icon_url=guild.icon.url if guild.icon else "")

            for group_id, data in groups.items():
                embed.add_field(name=f"{data['groupName']} ({group_id})", value=data["dmMessage"], inline=False)

            await response.send(embed=embed)
