from resources.structures.Bloxlink import Bloxlink  # pylint: disable=import-error, no-name-in-module
from resources.exceptions import Error, RobloxNotFound  # pylint: disable=import-error, no-name-in-module
from resources.constants import NICKNAME_TEMPLATES  # pylint: disable=import-error, no-name-in-module
from aiotrello.exceptions import TrelloUnauthorized, TrelloNotFound, TrelloBadRequest


get_group, parse_trello_binds = Bloxlink.get_module("roblox", attrs=["get_group", "parse_trello_binds"])



@Bloxlink.command
class GuestRoleCommand(Bloxlink.Module):
    """bind a discord role to non-group members"""

    def __init__(self):
        self.arguments = [
            {
                "prompt": "Please specify the **Group ID** to integrate with. The group ID is the rightmost numbers on your Group URL.",
                "slash_desc": "Please enter your Group ID.",
                "name": "group_id",
                "type": "number",
            },
            {
                "prompt": "Please specify the **role name** to bind non-group members. A role will be created if it doesn't already exist.",
                "slash_desc": "Please choose the role to bind to non-group members.",
                "name": "role",
                "type": "role"
            },
            {
                "prompt": "Should these members be given a nickname different from the server-wide `!nickname`? Please specify a nickname, or "
                          "say `skip` to skip this option and default to the server-wide nickname `!nickname` template.\n\nYou may use these templates:"
                          f"```{NICKNAME_TEMPLATES}```",
                "slash_desc": "Please enter a nickname to give to these members.",
                "slash_optional": True,
                "name": "nickname",
                "type": "string",
                "max": 100,
                "formatting": False
            },
            {
                "prompt": "Should any roles be **removed from the user** if they aren't in the group? You can specify multiple roles.\n\n"
                          "Note that this is an **advanced option**, so you most likely should `skip` this.",
                "slash_desc": "Should any roles be removed from the user?",
                "name": "remove_roles",
                "slash_optional": True,
                "multiple": True,
                "type": "role",
                "max": 10,
                "exceptions": ("skip",),
                "footer": "Say **skip** to skip this option."
            }
        ]

        self.permissions = Bloxlink.Permissions().build("BLOXLINK_MANAGER")
        self.category = "Binds"
        self.aliases = ["guestbind", "guest-role", "guest-bind"]
        self.slash_enabled = True

    async def __main__(self, CommandArgs):
        guild = CommandArgs.guild
        response = CommandArgs.response
        trello_board = CommandArgs.trello_board

        group_id = str(CommandArgs.parsed_args["group_id"])
        role = CommandArgs.parsed_args["role"]
        nickname = CommandArgs.parsed_args["nickname"]
        remove_roles = [str(r.id) for r in CommandArgs.parsed_args["remove_roles"]] if (CommandArgs.parsed_args["remove_roles"] and CommandArgs.parsed_args["remove_roles"] != "skip") else []
        remove_roles_trello = [str(r) for r in CommandArgs.parsed_args["remove_roles"]] if remove_roles and CommandArgs.parsed_args["remove_roles"] != "skip" else []

        nickname_lower = nickname and nickname.lower()
        role_id = str(role.id)

        try:
            group = await get_group(group_id, full_group=False)
        except RobloxNotFound:
            raise Error(f"A group with ID `{group_id}` does not exist. Please try again.")

        guild_data = CommandArgs.guild_data

        if trello_board:
            trello_binds_list = await trello_board.get_list(lambda l: l.name.lower() == "bloxlink binds")

            if not trello_binds_list:
                try:
                    trello_binds_list = await trello_board.create_list(name="Bloxlink Binds")
                except TrelloUnauthorized:
                        await response.error("In order for me to create Trello binds, please add `@bloxlink` to your "
                                             "Trello board.")
                except (TrelloNotFound, TrelloBadRequest):
                    pass

            trello_card_binds, _ = await parse_trello_binds(trello_board=trello_board, trello_binds_list=trello_binds_list)
        else:
            trello_binds_list = None
            trello_card_binds = {
                "groups": {
                    "entire group": {},
                    "binds": {}
                }
            }

        role_binds = guild_data.get("roleBinds") or {}

        if isinstance(role_binds, list):
            role_binds = role_binds[0]

        role_binds["groups"] = role_binds.get("groups") or {} # {"groups": {"ranges": {}, "binds": {}}}
        role_binds["groups"][group_id] = role_binds["groups"].get(group_id) or {}
        role_binds["groups"][group_id]["binds"] = role_binds["groups"][group_id].get("binds") or {}

        x = "0"

        rank = role_binds["groups"][group_id].get("binds", {}).get(x, {})

        if not isinstance(rank, dict):
            rank = {"nickname": nickname if nickname and nickname_lower not in ("skip", "done") else None, "roles": [str(rank)], "removeRoles": remove_roles}

            if role_id not in rank["roles"]:
                rank["roles"].append(role_id)
        else:
            if role_id not in rank.get("roles", []):
                rank["roles"] = rank.get("roles") or []
                rank["roles"].append(role_id)

            if nickname and nickname_lower not in ("skip", "done"):
                rank["nickname"] = nickname
            else:
                if not rank.get("nickname"):
                    rank["nickname"] = None

            rank["removeRoles"] = remove_roles

        role_binds["groups"][group_id]["binds"][x] = rank

        if trello_binds_list:
            make_binds_card = True

            if trello_card_binds:
                trello_bind_group = trello_card_binds["groups"]["binds"].get(group_id, {}).get("binds")

                if trello_bind_group:
                    card_data_ = trello_bind_group.get(x)
                    if card_data_:
                        for card in card_data_["trello"]["cards"]:
                            trello_card = card["card"]
                            trello_ranks = card.get("ranks", [])

                            if (x in trello_ranks or x == "all") and len(trello_ranks) == 1:
                                trello_bind_roles = card.get("roles", set())
                                card_bind_data = [
                                    f"Group: {group_id}",
                                    f"Nickname: {(nickname != 'skip' and nickname) or rank.get('nickname') or card_data_.get('nickname') or 'None'}",
                                ]

                                if remove_roles:
                                    card_bind_data.append(f"Remove roles: {', '.join(remove_roles_trello)}")

                                for role_ in trello_bind_roles:
                                    if role_ in (role_id, role.name):
                                        break
                                else:
                                    trello_bind_roles.add(role.name)
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
                    f"Roles: {role.name}",
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


        await self.r.table("guilds").insert({
            "id": str(guild.id),
            "roleBinds": role_binds
        }, conflict="update").run()


        await response.success(f"Successfully bound this **Guest Role** to role **{role.name}!**")