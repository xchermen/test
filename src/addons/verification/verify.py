from resources.structures.Bloxlink import Bloxlink # pylint: disable=import-error, no-name-in-module
import discord
from resources.exceptions import Message, UserNotVerified, Error, RobloxNotFound, BloxlinkBypass, Blacklisted, PermissionError # pylint: disable=import-error, no-name-in-module
from resources.constants import (NICKNAME_TEMPLATES, GREEN_COLOR, BROWN_COLOR, ARROW, VERIFY_URL, # pylint: disable=import-error, no-name-in-module
                                ACCOUNT_SETTINGS_URL, TRELLO)
from aiotrello.exceptions import TrelloNotFound, TrelloUnauthorized, TrelloBadRequest

verify_as, get_user, get_nickname, get_roblox_id, parse_accounts, unverify_member, format_update_embed, guild_obligations = Bloxlink.get_module("roblox", attrs=["verify_as", "get_user", "get_nickname", "get_roblox_id", "parse_accounts", "unverify_member", "format_update_embed", "guild_obligations"])
get_options = Bloxlink.get_module("trello", attrs="get_options")
post_event = Bloxlink.get_module("utils", attrs=["post_event"])



class VerifyCommand(Bloxlink.Module):
    """link your Roblox account to your Discord account and get your server roles"""

    def __init__(self):
        self.examples = ["add", "unlink", "view", "blox_link"]
        self.category = "Account"
        self.cooldown = 5
        self.dm_allowed = True
        self.slash_enabled = True
        self.slash_defer = True

    @staticmethod
    async def validate_username(message, content):
        try:
            roblox_id, username = await get_roblox_id(content)
        except RobloxNotFound:
            return None, "There was no Roblox account found with that username. Please try again."

        return username

    @Bloxlink.flags
    async def __main__(self, CommandArgs):
        trello_board = CommandArgs.trello_board
        guild_data = CommandArgs.guild_data
        guild = CommandArgs.guild
        author = CommandArgs.author
        response = CommandArgs.response
        prefix = CommandArgs.prefix

        if not guild:
            return await self.add(CommandArgs)

        if CommandArgs.flags.get("add") or CommandArgs.flags.get("verify") or CommandArgs.flags.get("force"):
            await CommandArgs.response.error(f"`{CommandArgs.prefix}verify --force` is deprecated and will be removed in a future version of Bloxlink. "
                                             f"Please use `{prefix}verify add` instead.")

            return await self.add(CommandArgs)

        if CommandArgs.real_command_name in ("getrole", "getroles"):
            CommandArgs.string_args = []

        trello_options = {}

        if trello_board:
            trello_options, _ = await get_options(trello_board)
            guild_data.update(trello_options)

        try:
            old_nickname = author.display_name

            added, removed, nickname, errors, warnings, roblox_user = await guild_obligations(
                CommandArgs.author,
                join                 = True,
                guild                = guild,
                guild_data           = guild_data,
                roles                = True,
                nickname             = True,
                trello_board         = CommandArgs.trello_board,
                cache                = False,
                response             = response,
                dm                   = False,
                exceptions           = ("BloxlinkBypass", "Blacklisted", "UserNotVerified", "PermissionError", "RobloxDown", "RobloxAPIError")
            )

        except BloxlinkBypass:
            raise Message("Since you have the `Bloxlink Bypass` role, I was unable to update your roles/nickname.", type="info")

        except Blacklisted as b:
            if isinstance(b.message, str):
                raise Error(f"{author.mention} has an active restriction for: `{b}`")
            else:
                raise Error(f"{author.mention} has an active restriction from Bloxlink.")

        except UserNotVerified:
            await self.add(CommandArgs)

        except PermissionError as e:
            raise Error(e.message)

        else:
            welcome_message, embed, view = await format_update_embed(roblox_user, author, added=added, removed=removed, errors=errors, warnings=warnings, nickname=nickname if old_nickname != nickname else None, prefix=prefix, guild_data=guild_data)

            await post_event(guild, guild_data, "verification", f"{author.mention} ({author.id}) has **verified** as `{roblox_user.username}`.", GREEN_COLOR)

            await response.send(content=welcome_message, embed=embed, view=view, mention_author=True)


    @Bloxlink.subcommand()
    async def add(self, CommandArgs):
        """link a new account to Bloxlink"""

        if CommandArgs.guild:
            guild_data = CommandArgs.guild_data

            if not guild_data.get("hasBot"):
                guild_data["hasBot"] = True

                await self.r.table("guilds").insert(guild_data, conflict="update").run()

        view = discord.ui.View()
        view.add_item(item=discord.ui.Button(style=discord.ButtonStyle.link, label="Verify with Bloxlink", url=VERIFY_URL, emoji="🔗"))
        view.add_item(item=discord.ui.Button(style=discord.ButtonStyle.link, label="Stuck? See a Tutorial", emoji="❔",
                                             url="https://www.youtube.com/watch?v=0SH3n8rY9Fg&list=PLz7SOP-guESE1V6ywCCLc1IQWiLURSvBE&index=2"))

        await CommandArgs.response.send("To verify with Bloxlink, click the link below.", mention_author=True, view=view)


    @Bloxlink.subcommand(permissions=Bloxlink.Permissions().build("BLOXLINK_MANAGER"))
    async def customize(self, CommandArgs):
        """customize the behavior of !verify"""

        # TODO: able to set: "forced groups"

        prefix = CommandArgs.prefix
        response = CommandArgs.response

        author = CommandArgs.author

        guild = CommandArgs.guild
        guild_data = CommandArgs.guild_data

        if not guild:
            return await response.send("This sub-command can only be used in a server!")

        choice = (await CommandArgs.prompt([{
            "prompt": "Which option would you like to change?\nOptions: `(welcomeMessage)`",
            "name": "choice",
            "type": "choice",
            "choices": ("welcomeMessage",)
        }]))["choice"]


        trello_board = CommandArgs.trello_board
        card = None

        if trello_board:
            options_trello_data, trello_binds_list = await get_options(trello_board, return_cards=True)
            options_trello_find = options_trello_data.get(choice)

            if options_trello_find:
                card = options_trello_find[1]

        if choice == "welcomeMessage":
            welcome_message = (await CommandArgs.prompt([{
                "prompt": f"What would you like your welcome message to be? This will be shown in `{prefix}verify` messages.\nYou may "
                          f"use these templates: ```{NICKNAME_TEMPLATES}```",
                "name": "welcome_message",
                "formatting": False,
                "max": 1500
            }], last=True))["welcome_message"]

            if trello_board and trello_binds_list:
                try:
                    if card:
                        if card.name == choice:
                            await card.edit(name="welcomeMessage", desc=welcome_message)
                    else:
                        trello_settings_list = await trello_board.get_list(lambda L: L.name == "Bloxlink Settings") \
                                            or await trello_board.create_list(name="Bloxlink Settings")

                        await trello_settings_list.create_card(name="welcomeMessage", desc=welcome_message)

                    await trello_binds_list.sync(card_limit=TRELLO["CARD_LIMIT"])

                except TrelloUnauthorized:
                    await response.error("In order for me to edit your Trello settings, please add `@bloxlink` to your "
                                         "Trello board.")

                except (TrelloNotFound, TrelloBadRequest):
                    pass

            await self.r.table("guilds").insert({
                "id": str(guild.id),
                "welcomeMessage": welcome_message
            }, conflict="update").run()

        await post_event(guild, guild_data, "configuration", f"{author.mention} ({author.id}) has **changed** the `{choice}`.", BROWN_COLOR)

        raise Message(f"Successfully saved your new `{choice}`!", type="success")


    @staticmethod
    @Bloxlink.subcommand()
    async def view(CommandArgs):
        """view your linked account(s)"""

        author = CommandArgs.author
        response = CommandArgs.response

        try:
            primary_account, accounts = await get_user("username", author=author, everything=False, basic_details=True)
        except UserNotVerified:
            raise Message("You have no accounts linked to Bloxlink!", type="info")
        else:
            accounts = list(accounts)

            parsed_accounts = await parse_accounts(accounts, reverse_search=True)
            parsed_accounts_str = []
            primary_account_str = "No primary account set"

            for roblox_username, roblox_data in parsed_accounts.items():
                if roblox_data[1]:
                    username_str = []

                    for discord_account in roblox_data[1]:
                        username_str.append(f"{discord_account} ({discord_account.id})")

                    username_str = ", ".join(username_str)

                    if primary_account and roblox_username == primary_account.username:
                        primary_account_str = f"**{roblox_username}** {ARROW} {username_str}"
                    else:
                        parsed_accounts_str.append(f"**{roblox_username}** {ARROW} {username_str}")

                else:
                    parsed_accounts_str.append(f"**{roblox_username}**")

            parsed_accounts_str = "\n".join(parsed_accounts_str)


            embed = discord.Embed(title="Linked Roblox Accounts")
            embed.add_field(name="Primary Account", value=primary_account_str)
            embed.add_field(name="Secondary Accounts", value=parsed_accounts_str or "No secondary account saved")
            embed.set_author(name=author, icon_url=author.avatar.url)

            await response.send(embed=embed, dm=True, strict_post=True)

    @staticmethod
    @Bloxlink.subcommand()
    async def unlink(CommandArgs):
        """unlink an account from Bloxlink"""

        if CommandArgs.guild:
            await CommandArgs.response.reply(f"to manage your accounts, please visit our website: <{ACCOUNT_SETTINGS_URL}>", mention_author=True)
        else:
            await CommandArgs.response.send(f"To manage your accounts, please visit our website: <{ACCOUNT_SETTINGS_URL}>", mention_author=True)
