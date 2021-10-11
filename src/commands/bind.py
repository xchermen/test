import re
import discord
from resources.exceptions import CancelledPrompt # pylint: disable=import-error, no-name-in-module
from resources.structures.Bloxlink import Bloxlink # pylint: disable=import-error, no-name-in-module
from resources.exceptions import PermissionError, Error, RobloxNotFound, RobloxAPIError, Message  # pylint: disable=import-error, no-name-in-module
from resources.constants import NICKNAME_TEMPLATES, ARROW, LIMITS, BLURPLE_COLOR, BROWN_COLOR  # pylint: disable=import-error, no-name-in-module
from aiotrello.exceptions import TrelloUnauthorized, TrelloNotFound, TrelloBadRequest

bind_num_range = re.compile(r"([0-9]+)\-([0-9]+)")
roblox_group_regex = re.compile(r"roblox.com/groups/(\d+)/")

get_group, parse_trello_binds, count_binds, get_binds = Bloxlink.get_module("roblox", attrs=["get_group", "parse_trello_binds", "count_binds", "get_binds"])
fetch, post_event = Bloxlink.get_module("utils", attrs=["fetch", "post_event"])
get_features = Bloxlink.get_module("premium", attrs=["get_features"])
clear_guild_data = Bloxlink.get_module("cache", attrs=["clear_guild_data"])

API_URL = "https://api.roblox.com"
FREE_BIND_COUNT, PREM_BIND_COUNT = LIMITS["BINDS"]["FREE"], LIMITS["BINDS"]["PREMIUM"]

@Bloxlink.command
class BindCommand(Bloxlink.Module):
    """bind a discord role to a roblox group, asset, or badge"""

    def __init__(self):
        self.aliases = ["newbind"]
        self.permissions = Bloxlink.Permissions().build("BLOXLINK_MANAGER")
        self.category = "Binds"
        self.slash_enabled = True

    @staticmethod
    def find_range(range_set, ranges):
        low = int(range_set[0])
        high = int(range_set[1])

        for i, range_ in enumerate(ranges):
            if range_["low"] == low and range_["high"] == high:
                return range_, i

        return {}, 0

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

    async def __main__(self, CommandArgs):
        guild = CommandArgs.guild
        response = CommandArgs.response
        guild_data = CommandArgs.guild_data
        trello_board = CommandArgs.trello_board
        prefix = CommandArgs.prefix
        author = CommandArgs.author
        locale = CommandArgs.locale

        role_binds_trello, group_ids_trello, trello_binds_list = await get_binds(guild=guild, trello_board=trello_board)

        bind_count = count_binds(guild_data, role_binds=role_binds_trello, group_ids=group_ids_trello)

        if bind_count >= FREE_BIND_COUNT:
            profile, _ = await get_features(discord.Object(id=guild.owner_id), guild=guild)

            if not profile.features.get("premium"):
                raise Error(locale("commands.bind.errors.noPremiumBindLimitExceeded", prefix=prefix, free_bind_count=FREE_BIND_COUNT, prem_bind_count=PREM_BIND_COUNT))

            if bind_count >= PREM_BIND_COUNT:
                raise Error(locale("commands.bind.errors.premiumBindLimitExceeded", prefix=prefix, prem_bind_count=PREM_BIND_COUNT))

        parsed_args = await CommandArgs.prompt([
            {
                "prompt": f"{locale('commands.bind.prompts.bindTypePrompt.line_1', arrow=ARROW)}\n",
                "name": "bind_choice",
                "type": "choice",
                "components": [discord.ui.Select(max_values=1, options=[
                        discord.SelectOption(label="Group", description="Users of your group will get a role."),
                        discord.SelectOption(label="Asset", description="Users need to own this catalog item."),
                        discord.SelectOption(label="Badge", description="Users need to own this badge."),
                        discord.SelectOption(label="GamePass", description="Users need to own this GamePass."),
                        discord.SelectOption(label="DevForum Members", description="Users need to be a member of the DevForum."),
                        discord.SelectOption(label="Roblox Staff", description="Users need to be Roblox Staff members."),
                    ])],
                "choices": locale("commands.bind.prompts.bindTypePrompt.choices"),
                "formatting": False
            },
            {
                "prompt": locale("commands.bind.prompts.nicknamePrompt.line", prefix=prefix, nickname_templates=NICKNAME_TEMPLATES),
                "name": "nickname",
                "max": 100,
                "type": "string",
                "footer": locale("commands.bind.prompts.nicknamePrompt.footer"),
                "formatting": False
            },
            {
                "prompt": "Should any **additional** roles be **removed from the user** if they meet the bind conditions? You can specify multiple roles.\n\n"
                          "Note that this is an **advanced option**, so you most likely should `skip` this. Bloxlink will already remove \"old\" Group roles.\n\n"
                          "This option really exists if there are non-group roles that another bot in your server gives.",
                "name": "remove_roles",
                "multiple": True,
                "type": "role",
                "max": 10,
                "exceptions": ("skip",),
                "footer": "Say **skip** to skip this option."
            }
        ])

        bind_choice = parsed_args["bind_choice"][0].lower()
        nickname = parsed_args["nickname"]

        if "display-name" in nickname:
            display_name_confirm = (await CommandArgs.prompt([{
                "prompt": "**Warning!** You chose Display Names for your Nickname Template.\n"
                          "Display Names **aren't unique** and can **lead to impersonation.** Are you sure you want to use this? yes/no",
                "type": "choice",
                "components": [discord.ui.Select(max_values=1, options=[
                        discord.SelectOption(label="Yes"),
                        discord.SelectOption(label="No"),
                    ])],
                "choices": ("yes", "no"),
                "name": "confirm",
                "embed_title": "Display Names Confirmation",
                "embed_color": BROWN_COLOR,
                "formatting": False
            }]))["confirm"][0]

            if display_name_confirm == "no":
                raise CancelledPrompt

        remove_roles = [str(r.id) for r in parsed_args["remove_roles"]] if parsed_args["remove_roles"] != "skip" else []
        remove_roles_trello = [str(r) for r in parsed_args["remove_roles"]] if parsed_args["remove_roles"] != "skip" else []

        if trello_board:
            trello_binds_list = await trello_board.get_list(lambda l: l.name.lower() == "bloxlink binds")

            if not trello_binds_list:
                try:
                    trello_binds_list = await trello_board.create_list(name="Bloxlink Binds")
                except TrelloUnauthorized:
                        await response.error(locale("commands.bind.errors.trelloError"))
                except (TrelloNotFound, TrelloBadRequest):
                    pass

            trello_card_binds, _ = await parse_trello_binds(trello_board=trello_board, trello_binds_list=trello_binds_list)
        else:
            trello_binds_list = None
            trello_group_bind = None
            trello_card_binds = {
                "groups": {
                    "entire group": {},
                    "binds": {}
                },
                "assets": {},
                "badges": {},
                "gamePasses": {}
            }

        if nickname.lower() in (locale("prompt.skip"), locale("prompt.done"), locale("prompt.next")):
            nickname = None
            nickname_lower = None
        else:
            nickname_lower = nickname.lower()

        if bind_choice == locale("commands.bind.group"):
            parsed_args_group = await CommandArgs.prompt([
                {
                    "prompt": locale("commands.bind.prompts.groupPrompt.line"),
                    "name": "group",
                    "validation": self.validate_group
                },
                {
                "prompt": f"{locale('commands.bind.prompts.groupBindMode.line_1', arrow=ARROW)}\n"
                          f"{locale('commands.bind.prompts.groupBindMode.line_2', arrow=ARROW)}\n"
                          f"{locale('commands.bind.prompts.groupBindMode.line_3', arrow=ARROW)}",
                    "name": "type",
                    "components": [discord.ui.Select(max_values=1, options=[
                            discord.SelectOption(label="Link my entire group", description="Roleset names must match with Discord role names."),
                            discord.SelectOption(label="Select specific rolesets", description="You can choose how the roles are called."),
                        ])],
                    "type": "choice",
                    "choices": ("link my entire group", "select specific rolesets")
                }
            ])

            group = parsed_args_group["group"]
            group_id = group.group_id

            group_ids = guild_data.get("groupIDs", {})
            found_group = trello_card_binds["groups"]["entire group"].get(group_id) or group_ids.get(group_id)

            trello_group_bind = trello_card_binds["groups"]["entire group"].get(group_id)

            if parsed_args_group["type"][0] == "link my entire group":
                if found_group:
                    if (nickname and found_group["nickname"] != nickname) or (sorted(remove_roles) != sorted(found_group.get("removeRoles", []))):
                        group_ids[group_id] = {"nickname": nickname, "groupName": group.name, "removeRoles": remove_roles}
                        guild_data["groupIDs"] = group_ids

                        await self.r.table("guilds").insert(guild_data, conflict="update").run()

                        trello_group_bind = trello_card_binds["groups"]["entire group"].get(group_id)

                        make_trello_card = True

                        if trello_group_bind and trello_group_bind["nickname"]:
                            for card_data in trello_group_bind["trello"].get("cards", []):
                                card = card_data["card"]

                                try:
                                    await card.edit(desc=card.description.replace(trello_group_bind["nickname"], nickname or 'None'))
                                except TrelloUnauthorized:
                                    await response.error("In order for me to edit your Trello binds, please add `@bloxlink` to your "
                                                         "Trello board.")
                                except (TrelloNotFound, TrelloBadRequest):
                                    pass

                                make_trello_card = False

                            if make_trello_card:
                                card_bind_data = [
                                    f"Group: {group_id}",
                                    f"Nickname: {nickname}"
                                ]

                                if remove_roles:
                                    card_bind_data.append(f"Remove roles: {', '.join(remove_roles_trello)}")

                                try:
                                    await trello_binds_list.create_card(name="Bloxlink Group Bind", desc="\n".join(card_bind_data))
                                except TrelloUnauthorized:
                                    await response.error("In order for me to edit your Trello binds, please add `@bloxlink` to your "
                                                         "Trello board.")
                                except (TrelloNotFound, TrelloBadRequest):
                                    pass

                            if trello_binds_list:
                                trello_binds_list.parsed_bind_data = None

                        ending_s = group.name.endswith("s") and "'" or "'s"

                        await post_event(guild, guild_data, "bind", f"{author.mention} ({author.id}) has **changed** `{group.name}`{ending_s} nickname template.", BLURPLE_COLOR)

                        await clear_guild_data(guild)

                        raise Message("Since your group is already linked, the nickname was updated.", type="success")

                    else:
                        raise Message("This group is already linked!", type="silly")

                for _, roleset_data in group.rolesets.items():
                    discord_role = discord.utils.find(lambda r: r.name == roleset_data[0], guild.roles)

                    if not discord_role:
                        try:
                            discord_role = await guild.create_role(name=roleset_data[0])
                        except discord.errors.Forbidden:
                            raise PermissionError("I was unable to create the Discord role. Please ensure my role has the `Manage Roles` permission.")

                # add group to guild_data.groupIDs
                group_ids[group_id] = {"nickname": nickname not in ("skip", "next") and nickname, "groupName": group.name, "removeRoles": remove_roles}
                guild_data["groupIDs"] = group_ids

                await self.r.table("guilds").insert(guild_data, conflict="update").run()

                if trello_binds_list:
                    card_bind_data = [
                        f"Group: {group_id}",
                        f"Nickname: {nickname}"
                    ]

                    if remove_roles:
                        card_bind_data.append(f"Remove roles: {', '.join(remove_roles_trello)}")

                    try:
                        await trello_binds_list.create_card(name="Bloxlink Group Bind", desc="\n".join(card_bind_data))
                    except TrelloUnauthorized:
                        await response.error("In order for me to edit your Trello binds, please add `@bloxlink` to your "
                                             "Trello board.")
                    except (TrelloNotFound, TrelloBadRequest):
                        pass

                await post_event(guild, guild_data, "bind", f"{author.mention} ({author.id}) has **linked** group `{group.name}`.", BLURPLE_COLOR)
                await clear_guild_data(guild)

                raise Message("Success! Your group was successfully linked.", type="success")

            else:
                # select ranks from their group
                # ask if they want to auto-create the binds or select a specific role
                # shows confirmation embed with arrows from rank to discord role

                discord_role = await CommandArgs.prompt([
                    {
                        "prompt": "Please provide **Discord role name(s)** for this bind, separated by commas.",
                        "name": "role",
                        "type": "role",
                        "multiple": True,
                        "max": 10
                    }
                ])

                discord_roles = discord_role["role"]
                new_ranks = {"binds":[], "ranges": []}
                role_binds = guild_data.get("roleBinds") or {}

                if isinstance(role_binds, list):
                    role_binds = role_binds[0]

                role_binds["groups"] = role_binds.get("groups") or {} # {"groups": {"ranges": {}, "binds": {}}}
                role_binds["groups"][group_id] = role_binds["groups"].get(group_id) or {}
                role_binds["groups"][group_id]["binds"] = role_binds["groups"][group_id].get("binds") or {}
                role_binds["groups"][group_id]["ranges"] = role_binds["groups"][group_id].get("ranges") or {}
                role_binds["groups"][group_id]["groupName"] = group.name
                role_binds["groups"][group_id]["removeRoles"] = remove_roles

                rolesets_embed = discord.Embed(title=f"{group.name} Rolesets", description="\n".join(f"**{x[0]}** {ARROW} {x[1]}" for x in group.rolesets.values()))
                rolesets_embed = await CommandArgs.response.send(embed=rolesets_embed)
                response.delete(rolesets_embed)

                failures = 0

                while True:
                    if failures == 5:
                        raise Error("Too many failed attempts. Please run this command again.")

                    selected_ranks = await CommandArgs.prompt([
                        {
                            "prompt": f"Please select the rolesets that should receive the role(s) **{', '.join([r.name for r in discord_roles])}**. "
                                       "You may specify the roleset name or ID. You may provide them in a list, "
                                       "or as a range. You may also say `everyone` to capture everyone in the group; "
                                       "and you can negate the number to catch everyone with the rank _and above._\n"
                                       "You can also say `guest` to include **all non-group members**.\n\n"
                                       "Example 1: `1,4,-6,VIP, 10, 50-100, Staff Members, 255`.\nExample 2: `"
                                       "-100` means everyone with rank 100 _and above._\nExample 3: `everyone` "
                                       "means everyone in the group.\n\n"
                                       "For your convenience, your Rolesets' names and IDs were sent above.",
                            "name": "ranks",
                            "formatting": False

                        }
                    ], last=True)

                    for rank in selected_ranks["ranks"].split(","):
                        rank = rank.strip()

                        if rank.isdigit() and rank != "0":
                            if 1 <= int(rank) <= 255:
                                new_ranks["binds"].append(str(rank))
                            else:
                                response.delete(await response.error("Ranks must be an integer between [1-255]"))
                                failures += 1
                                break
                        elif rank in ("all", "everyone"):
                            new_ranks["binds"].append("all")
                        elif rank in ("0", "guest"):
                            new_ranks["binds"].append("0")
                        elif rank[:1] == "-":
                            try:
                                int(rank)
                            except ValueError:
                                pass
                            else:
                                new_ranks["binds"].append(rank)
                        else:
                            range_search = bind_num_range.search(rank)

                            if range_search:
                                num1, num2 = range_search.group(1), range_search.group(2)
                                if (1 <= int(num1) <= 255) and (1 <= int(num2) <= 255):
                                    new_ranks["ranges"].append([num1, num2])
                                else:
                                    response.delete(await response.error("Ranges must be between [1-255]."))
                                    failures += 1
                                    break
                            else:
                                # they specified a roleset name as a string
                                roleset_find = group.rolesets.get(rank.lower())

                                if roleset_find:
                                    new_ranks["binds"].append(str(roleset_find[1]))
                                else:
                                    response.delete(await response.error("Could not find a matching Roleset name. Please try again."))
                                    failures += 1
                                    break
                    else:
                        break

                if new_ranks["binds"]:
                    for x in new_ranks["binds"]:
                        rank = role_binds["groups"][group_id].get("binds", {}).get(x, {})

                        if not isinstance(rank, dict):
                            rank = {"nickname": nickname_lower, "roles": [str(rank)], "removeRoles": remove_roles}

                            for discord_role in discord_roles:
                                role_id = str(discord_role.id)

                                if role_id not in rank["roles"]:
                                    rank["roles"].append(role_id)
                        else:
                            for discord_role in discord_roles:
                                role_id = str(discord_role.id)

                                if role_id not in rank.get("roles", []):
                                    rank["roles"] = rank.get("roles") or []
                                    rank["roles"].append(role_id)

                            if nickname_lower:
                                rank["nickname"] = nickname
                            else:
                                if not rank.get("nickname"):
                                    rank["nickname"] = None

                            rank["removeRoles"] = remove_roles

                        role_binds["groups"][group_id]["binds"][x] = rank
                        # trello binds:
                            # rank is in list of ranks
                                # update nickname
                                # append role
                            # else: make new card

                        if trello_binds_list:
                            make_binds_card = True

                            if trello_card_binds:
                                trello_bind_group = trello_card_binds["groups"]["binds"].get(group_id, {}).get("binds")

                                if trello_bind_group:
                                    card_data_ = trello_bind_group.get(x)

                                    if card_data_:
                                        for card in card_data_.get("trello", {}).get("cards", []):
                                            trello_card = card["card"]
                                            trello_ranks = card.get("ranks") or []

                                            if (x in trello_ranks or x == "all") and len(trello_ranks) == 1:
                                                trello_bind_roles = card.get("roles", set())
                                                card_bind_data = [
                                                    f"Group: {group_id}",
                                                    f"Nickname: {(nickname != 'skip' and nickname) or rank.get('nickname') or card_data_.get('nickname') or 'None'}",
                                                ]

                                                if remove_roles:
                                                    card_bind_data.append(f"Remove roles: {', '.join(remove_roles_trello)}")

                                                for discord_role in discord_roles:
                                                    trello_bind_roles.add(discord_role.name)

                                                card_bind_data.append(f"Roles: {', '.join(trello_bind_roles)}")
                                                card_bind_data.append(f"Ranks: {card['trello_str']['ranks']}")

                                                trello_card_desc = "\n".join(card_bind_data)

                                                if trello_card_desc != trello_card.description:
                                                    trello_card.description = trello_card_desc

                                                    try:
                                                        await trello_card.edit(desc=trello_card_desc)
                                                    except TrelloUnauthorized:
                                                        await response.error("In order for me to edit your Trello binds, please add `@bloxlink` to your "
                                                                             "Trello board.")
                                                    except (TrelloNotFound, TrelloBadRequest):
                                                        pass

                                                    trello_binds_list.parsed_bind_data = None
                                                    make_binds_card = False

                                                    break

                            if make_binds_card:
                                card_bind_data = [
                                    f"Group: {group_id}",
                                    f"Nickname: {nickname != 'skip' and nickname or 'None'}",
                                    f"Roles: {', '.join([r.name for r in discord_roles])}",
                                ]

                                if remove_roles:
                                    card_bind_data.append(f"Remove roles: {', '.join(remove_roles_trello)}")

                                if x != "all":
                                    card_bind_data.append(f"Ranks: {x}")

                                trello_card_desc = "\n".join(card_bind_data)

                                try:
                                    card = await trello_binds_list.create_card(name="Bloxlink Bind", desc=trello_card_desc)
                                except TrelloUnauthorized:
                                    await response.error("In order for me to edit your Trello binds, please add `@bloxlink` to your "
                                                         "Trello board.")
                                except (TrelloNotFound, TrelloBadRequest):
                                    pass

                                trello_binds_list.parsed_bind_data = None

                if new_ranks["ranges"]:
                    role_binds["groups"][group_id]["ranges"] = role_binds["groups"][group_id].get("ranges") or []

                    for x in new_ranks["ranges"]: # list of dictionaries: [{"high": 10, "low": 1, "nickname": ""},...]
                        range_, num = self.find_range(x, role_binds["groups"][group_id]["ranges"])
                        found = bool(range_)

                        for discord_role in discord_roles:
                            role_id = str(discord_role.id)

                            if not role_id in range_.get("roles", []):
                                range_["roles"] = range_.get("roles") or []
                                range_["roles"].append(role_id)

                        if nickname_lower:
                            range_["nickname"] = nickname
                        else:
                            if not range_.get("nickname"):
                                range_["nickname"] = None

                        range_["removeRoles"] = remove_roles

                        if found:
                            role_binds["groups"][group_id]["ranges"][num] = range_
                        else:
                            range_["low"] = int(x[0])
                            range_["high"] = int(x[1])
                            role_binds["groups"][group_id]["ranges"].append(range_)

                        if trello_binds_list:
                            make_binds_card = True

                            if trello_card_binds:
                                trello_range_group = trello_card_binds["groups"]["binds"].get(group_id, {}).get("ranges")

                                if trello_range_group:
                                    for trello_range in trello_range_group:
                                        trello_data = trello_range["trello"]

                                        for card in trello_data.get("cards", []):
                                            trello_card = card["card"]
                                            trello_ranks = card.get("ranks", [])

                                            if trello_range["low"] == range_["low"] and trello_range["high"] == range_["high"] and len(trello_ranks) == 1:
                                                trello_data = trello_range["trello"]
                                                trello_bind_roles = trello_range.get("roles", set())
                                                card_bind_data = [
                                                    f"Group: {group_id}",
                                                    f"Nickname: {(nickname != 'skip' and nickname) or trello_range.get('nickname') or 'None'}",
                                                ]

                                                if remove_roles:
                                                    card_bind_data.append(f"Remove roles: {', '.join(remove_roles_trello)}")

                                                for discord_role in discord_roles:
                                                    trello_bind_roles.add(discord_role.name)

                                                card_bind_data.append(f"Roles: {', '.join(trello_bind_roles)}")
                                                card_bind_data.append(f"Ranks: {card['trello_str']['ranks']}")

                                                trello_card_desc = "\n".join(card_bind_data)

                                                if trello_card_desc != trello_card.description:
                                                    trello_card.description = trello_card_desc

                                                    try:
                                                        await trello_card.edit(desc=trello_card_desc)
                                                    except TrelloUnauthorized:
                                                        await response.error("In order for me to edit your Trello binds, please add `@bloxlink` to your "
                                                                             "Trello board.")
                                                    except (TrelloNotFound, TrelloBadRequest):
                                                        pass

                                                    trello_binds_list.parsed_bind_data = None
                                                    make_binds_card = False

                                                    break

                            if make_binds_card:
                                card_bind_data = [
                                    f"Group: {group_id}",
                                    f"Nickname: {nickname != 'skip' and nickname or 'None'}",
                                    f"Roles: {', '.join([r.name for r in discord_roles])}",
                                    f"Ranks: {range_['low']}-{range_['high']}"
                                ]

                                if remove_roles:
                                    card_bind_data.append(f"Remove roles: {', '.join(remove_roles_trello)}")

                                trello_card_desc = "\n".join(card_bind_data)

                                try:
                                    card = await trello_binds_list.create_card(name="Bloxlink Range Bind", desc=trello_card_desc)
                                except TrelloUnauthorized:
                                    await response.error("In order for me to edit your Trello binds, please add `@bloxlink` to your "
                                                         "Trello board.")
                                except (TrelloNotFound, TrelloBadRequest):
                                    pass

                                trello_binds_list.parsed_bind_data = None


            await self.r.table("guilds").insert({
                "id": str(guild.id),
                "roleBinds": role_binds
            }, conflict="update").run()

            text = ["Successfully **bound** rank ID(s): `"]
            if new_ranks["binds"]:
                text.append(", ".join(new_ranks["binds"]))

            if new_ranks["ranges"]:
                text2 = ""

                if new_ranks["binds"]:
                    text2 = "; "

                text.append(f"{text2}ranges: {', '.join([r[0] + ' - ' + r[1] for r in new_ranks['ranges']])}")

            text.append(f"` with Discord role(s) **{', '.join([r.name for r in discord_roles])}**.")

            text = "".join(text)

            await post_event(guild, guild_data, "bind", f"{author.mention} ({author.id}) has **bound** group `{group.name}`.", BLURPLE_COLOR)

            await clear_guild_data(guild)

            await response.success(text)

        else:
            no_id_bind = False

            if bind_choice == "gamepass":
                bind_choice_title = "GamePass"
                bind_choice_plural = "gamePasses"
            elif bind_choice == "devforum members":
                bind_choice_title = "DevForum Members"
                bind_choice_plural = "devForum"
                no_id_bind = True
            elif bind_choice == "roblox staff":
                bind_choice_title = "Roblox Staff"
                bind_choice_plural = "robloxStaff"
                no_id_bind = True
            else:
                bind_choice_title = bind_choice.title()
                bind_choice_plural = f"{bind_choice}s"

            if not no_id_bind:
                vg_parsed_args_1 = await CommandArgs.prompt([
                    {
                        "prompt": f"Please provide the **{bind_choice_title} ID** to use for this bind.",
                        "name": "bind_id",
                        "type": "number",
                        "formatting": False
                    }
                ])

            vg_parsed_args_2 = await CommandArgs.prompt([
                {
                    "prompt": "Please provide **Discord role name(s)** for this bind, separated by commas.",
                    "name": "role",
                    "type": "role",
                    "multiple": True,
                    "max": 10
                },
            ], last=True)

            discord_roles = vg_parsed_args_2["role"]
            bind_id = str(vg_parsed_args_1["bind_id"]) if not no_id_bind else None
            display_name = None

            if bind_choice == "asset":
                try:
                    json_data, response_ = await fetch(f"{API_URL}/marketplace/productinfo?assetId={bind_id}", json=True)
                except (RobloxNotFound, RobloxAPIError):
                    raise Error(f"An Asset with ID `{bind_id}` does not exist.")

                display_name = json_data.get("Name")

            elif bind_choice == "badge":
                try:
                    json_data, response_ = await fetch(f"https://badges.roblox.com/v1/badges/{bind_id}", json=True)
                except (RobloxNotFound, RobloxAPIError):
                    raise Error(f"A Badge with ID `{bind_id}` does not exist.")

                display_name = json_data.get("displayName")

            elif bind_choice == "gamepass":
                bind_choice_title = "GamePass"
                bind_choice_plural = "gamePasses"

                try:
                    json_data, response_ = await fetch(f"http://api.roblox.com/marketplace/game-pass-product-info?gamePassId={bind_id}", json=True)
                except (RobloxNotFound, RobloxAPIError):
                    raise Error(f"A GamePass with ID `{bind_id}` does not exist.")

                if json_data.get("ProductType") != "Game Pass":
                    raise Error(f"A GamePass with ID `{bind_id}` does not exist.")

                display_name = json_data.get("Name")

            role_binds = guild_data.get("roleBinds") or {}

            if isinstance(role_binds, list):
                role_binds = role_binds[0]

            role_binds[bind_choice_plural] = role_binds.get(bind_choice_plural) or {}

            if bind_id:
                role_binds[bind_choice_plural][bind_id] = role_binds[bind_choice_plural].get(bind_id) or {}
                data_point = role_binds[bind_choice_plural][bind_id]
            else:
                role_binds[bind_choice_plural] = role_binds.get(bind_choice_plural) or {}
                data_point = role_binds[bind_choice_plural]

            data_point["nickname"] = nickname
            data_point["displayName"] = display_name
            data_point["removeRoles"] = remove_roles
            data_point["roles"] = data_point.get("roles", [])
            roles = data_point["roles"]

            for discord_role in discord_roles:
                role_id = str(discord_role.id)

                if not role_id in roles:
                    roles.append(role_id)


            if trello_binds_list:
                make_binds_card = True

                if trello_card_binds:
                    trello_bind_vg = trello_card_binds.get(bind_choice_plural, {}).get(bind_id)

                    if trello_bind_vg:
                        trello_bind_roles = set(trello_bind_vg.get("roles", set()))

                        for card in trello_bind_vg.get("trello", {})["cards"]:
                            trello_card = card["card"]

                            card_bind_data = [
                                f"{bind_choice_title} ID: {bind_id}",
                                f"Display Name: {display_name}",
                                f"Nickname: {(nickname != 'skip' and nickname) or trello_bind_vg.get('nickname') or 'None'}",
                            ]

                            for discord_role in discord_roles:
                                trello_bind_roles.add(discord_role.name)

                            card_bind_data.append(f"Roles: {', '.join(trello_bind_roles)}")

                            trello_card_desc = "\n".join(card_bind_data)

                            if trello_card_desc != trello_card.description:
                                trello_card.description = trello_card_desc

                                try:
                                    await trello_card.edit(desc=trello_card_desc)
                                except TrelloUnauthorized:
                                    await response.error("In order for me to edit your Trello binds, please add `@bloxlink` to your "
                                                         "Trello board.")
                                except (TrelloNotFound, TrelloBadRequest):
                                    pass

                                trello_binds_list.parsed_bind_data = None
                                make_binds_card = False

                                break

                if make_binds_card:
                    card_bind_data = [
                        f"{bind_choice_title} ID: {bind_id}",
                        f"Display Name: {display_name}",
                        f"Nickname: {nickname != 'skip' and nickname or 'None'}",
                        f"Roles: {', '.join([d.name for d in discord_roles])}",
                    ]

                    if remove_roles:
                        card_bind_data.append(f"Remove roles: {', '.join(remove_roles_trello)}")

                    trello_card_desc = "\n".join(card_bind_data)

                    try:
                        card = await trello_binds_list.create_card(name=f"Bloxlink {bind_choice_title} Bind", desc=trello_card_desc)
                    except TrelloUnauthorized:
                        await response.error("In order for me to edit your Trello binds, please add `@bloxlink` to your "
                                             "Trello board.")
                    except (TrelloNotFound, TrelloBadRequest):
                        pass

                    trello_binds_list.parsed_bind_data = None


            await self.r.table("guilds").insert({
                "id": str(guild.id),
                "roleBinds": role_binds
            }, conflict="update").run()

            await clear_guild_data(guild)

            if display_name:
                await post_event(guild, guild_data, "bind", f"{author.mention} ({author.id}) has **bound** {bind_choice_title} `{display_name}`.", BLURPLE_COLOR)
                await response.success(f"Successfully **bound** {bind_choice_title} `{display_name}` ({bind_id}) with Discord role(s) **{', '.join([r.name for r in discord_roles])}!**")
            else:
                await post_event(guild, guild_data, "bind", f"{author.mention} ({author.id}) has **bound** {bind_choice_title}.", BLURPLE_COLOR)
                await response.success(f"Successfully **bound** {bind_choice_title} with Discord role(s) **{', '.join([r.name for r in discord_roles])}!**")
