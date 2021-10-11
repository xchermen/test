import discord
from ..exceptions import CancelCommand, Error # pylint: disable=import-error, no-name-in-module
from ..structures import Bloxlink # pylint: disable=import-error, no-name-in-module
from asyncio import TimeoutError
import math

FAST_REWIND  = "<:FastRewind:872195337727660032>"
BACK         = "<:LeftArrow:872188452639244339>"
FORWARD      = "<:RightArrow:872188412596195338>"
FAST_FORWARD = "<:FastForward:872195378680832001>"


class InteractionPaginatorSelect(discord.ui.Select):
    def __init__(self, categories, paginator):
        self.paginator = paginator

        options = [
            discord.SelectOption(label=c, default = c == paginator.current_category) for c in categories
        ]

        super().__init__(placeholder=paginator.current_category, min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        self.paginator.current_category = self.values[0]

        await self.paginator.start_position()


class InteractionPaginator(discord.ui.View):
    def __init__(self, items, response, embed=discord.Embed(), max_items=5, use_fields=True, default_category=None, description=None):
        super().__init__()

        self.categories = list(items.keys())
        self.response = response
        self.embed = embed
        self.max_items = max_items
        self.items = items
        self.use_fields = use_fields
        self.description = description

        self.message = self.back_button = self.forward_button = self.fast_forward_button = self.fast_rewind_button = self.select_menu = None

        self.current_category = default_category or self.categories[0]

    async def fast_rewind_press(self, interaction):
       await self.start_position()

    async def fast_forward_press(self, interaction):
        all_items = self.items[self.current_category]

        self.i = math.ceil((len(all_items) / self.max_items)) * self.max_items

        current_items = all_items[self.i-self.max_items:self.i]

        self.populate_embed(current_items)

        self.check_buttons()

        self.back_button.disabled = False
        self.fast_rewind_button.disabled = False

        await self.message.edit(embed=self.embed, view=self)

    async def back_press(self, interaction):
        self.i = self.i-self.max_items

        all_items = self.items[self.current_category]
        current_items = all_items[self.i-self.max_items:self.i]

        self.populate_embed(current_items)

        self.check_buttons()

        self.forward_button.disabled = False
        self.fast_forward_button.disabled = False

        await self.message.edit(embed=self.embed, view=self)

    async def forward_press(self, interaction):
        all_items = self.items[self.current_category]
        current_items = all_items[self.i:self.i+self.max_items]

        self.i = self.i+self.max_items

        self.populate_embed(current_items)

        self.check_buttons()

        self.back_button.disabled = False
        self.fast_rewind_button.disabled = False

        await self.message.edit(embed=self.embed, view=self)

    def populate_embed(self, current_items):
        all_items = self.items[self.current_category]

        if self.description:
            self.embed.description = f"{self.description}\n\n"
        else:
            self.embed.description = ""

        if self.use_fields:
            self.embed.clear_fields()

            for entry in current_items:
                self.embed.add_field(name=entry[0], value=entry[1], inline=False)
        else:
            self.embed.description = self.embed.description + "\n".join(current_items)

        self.embed.set_footer(text=f"!help <command name> to view more information | Page {self.i // self.max_items} of {((math.ceil(len(all_items) / self.max_items)) or 1)}")

    def check_buttons(self):
        all_items = self.items[self.current_category]

        if self.i >= len(all_items):
            self.forward_button.disabled = True
            self.fast_forward_button.disabled = True

        if self.i == self.max_items:
            self.back_button.disabled = True
            self.fast_rewind_button.disabled = True

    async def start_position(self):
        self.i = 0

        all_items = self.items[self.current_category]
        current_items = all_items[self.i:self.i+self.max_items]

        self.i = self.i+self.max_items

        self.populate_embed(current_items)

        if self.back_button or self.forward_button:
            self.remove_item(self.back_button)
            self.remove_item(self.forward_button)
            self.remove_item(self.fast_rewind_button)
            self.remove_item(self.fast_forward_button)

        self.fast_rewind_button  = discord.ui.Button(emoji=FAST_REWIND, disabled=True, style=discord.ButtonStyle.primary)
        self.back_button         = discord.ui.Button(emoji=BACK, disabled=True, style=discord.ButtonStyle.primary)
        self.forward_button      = discord.ui.Button(emoji=FORWARD, style=discord.ButtonStyle.primary)
        self.fast_forward_button = discord.ui.Button(emoji=FAST_FORWARD, style=discord.ButtonStyle.primary)

        self.add_item(self.fast_rewind_button)
        self.add_item(self.back_button)
        self.add_item(self.forward_button)
        self.add_item(self.fast_forward_button)

        self.fast_rewind_button.callback  = self.fast_rewind_press
        self.back_button.callback         = self.back_press
        self.forward_button.callback      = self.forward_press
        self.fast_forward_button.callback = self.fast_forward_press

        self.check_buttons()

        if self.categories:
            if self.select_menu:
                self.remove_item(self.select_menu)

            self.select_menu = InteractionPaginatorSelect(self.categories, self)
            self.add_item(self.select_menu)

        if self.message:
            await self.message.edit(embed=self.embed, view=self)
        else:
            self.message = await self.response.send(embed=self.embed, view=self)

    async def __call__(self):
        await self.start_position()



class Paginate:
    """Smart paginator for Discord embeds"""

    def __init__(self, author, channel, embed, response=None, original_channel=None, field_limit=25, hidden=False, pages=None, dm=False):
        self.author = author
        self.embed = embed
        self.response = response
        self.original_channel = original_channel

        self.field_limit = field_limit
        self.channel = channel
        self._pages = pages
        self.dm = dm
        self.hidden = hidden

        self.sent_message = None

    @staticmethod
    def get_pages(embed, fields, field_limit=25):
        pages = []
        i = 0

        len_fields = len(fields)

        while True:
            remaining = 4000
            field = fields[i]
            current_page = []

            while remaining > 0 and i != len(fields):
                # get first 1024 characters, append, remove from old field
                # if the old field is gone, increment i
                # if it's 6000, append to pages and clear current_page, and reset remaining

                # check to see if there's room on the current page
                len_field_name = len(field.name)
                if remaining > len_field_name + 1:
                    # get first 1024 characters with respect to remaining
                    chars = field.value[0:min(500, remaining - len_field_name)]
                    len_chars = len(chars)
                    current_page.append({"name": field.name, "value": chars})
                    remaining -= len_chars
                    field.value = field.value[len_chars:] # remove characters

                    if not field.value:
                        # no more field, so get next one. there's still room for more, though
                        if i + 1 < len(fields):
                            i += 1
                            field = fields[i]
                        else:
                            break
                else:
                    # page is done
                    pages.append(current_page)
                    if not field.value:
                        i += 1

                    break

            if not field.value and len_fields <= i + 1:
                pages.append(current_page)

                break

        """
        current_page = []
        remaining = 5000
        skip_over = False

        for field in fields:
            while remaining:

                if remaining > len(field.name) + 1:
                    chars = field.value[0:min(1000, remaining - len(field.name))]
                    current_page.append({"name": field.name, "value": field.value})
                    field.value = field.value[len(chars):]
                    remaining -= len(chars)
                    if not field.value:
                        #skip_over = True

                        break

                else:
                    pages.append(current_page)
                    current_page = []
                    remaining = 5000
                    skip_over = True

                    break

                #chars = field.value[0:min(1000, remaining - len(field.name))]
                #current_page.append({"name": field.name, "value": field.value})

            if not skip_over:
                remaining = 5000
                pages.append(current_page)
                current_page = []
            else:
                skip_over = False


        """



        return pages

    async def turn_page(self, i, pages):
        self.embed.clear_fields()

        total = 0
        for field in pages[i]:
            self.embed.add_field(name=field["name"], value=field["value"], inline=False)

        if self.sent_message:
            try:
                await self.sent_message.edit(embed=self.embed)
            except (discord.errors.NotFound, discord.errors.Forbidden):
                raise CancelCommand
        else:
            self.sent_message = await self.response.send(embed=self.embed, channel_override=self.channel, ignore_http_check=True, hidden=self.hidden, reference=None, reply=False, mention_author=False)

            if not self.sent_message:
                return False

        return True

    async def __call__(self):
        send_to = self.original_channel or self.channel

        pages = self._pages or Paginate.get_pages(self.embed, self.embed.fields, self.field_limit)
        len_pages = len(pages)

        i = 0
        user = None

        success = await self.turn_page(i, pages)

        if success:
            if self.dm:
                await send_to.send(self.author.mention + ", **check your DMs!**")
        else:
            if self.dm:
                await send_to.send(self.author.mention + ", I was unable to DM you! Please check your privacy settings and try again.")
            else:
                await send_to.send(self.author.mention + ", I was unable to send the message. Please make sure I have the `Embed Links` permission.")

            raise CancelCommand


        if len_pages > 1:
            reactions = {'\N{BLACK LEFT-POINTING DOUBLE TRIANGLE WITH VERTICAL BAR}': lambda: 0,
                        '\N{BLACK LEFT-POINTING TRIANGLE}': lambda: i - 1 >= 0 and i - 1,
                        '\N{BLACK RIGHT-POINTING TRIANGLE}': lambda: i + 1 < len_pages and i + 1,
                        '\N{BLACK RIGHT-POINTING DOUBLE TRIANGLE WITH VERTICAL BAR}': lambda: len_pages - 1,
                        }

            for reaction in reactions:
                try:
                    await self.sent_message.add_reaction(reaction)
                except discord.errors.Forbidden:
                    raise Error("I'm missing the `Add Reactions` permission.")

            while True:
                try:
                    reaction, user = await Bloxlink.wait_for("reaction_add", check=lambda r, u: str(r) in reactions and u == self.author and \
                                                                                                r.message.id == self.sent_message.id, timeout=120)
                except TimeoutError:
                    try:
                        await self.sent_message.clear_reactions()
                        raise CancelCommand
                    except discord.errors.Forbidden:
                        raise Error("I'm missing the `Manage Messages` permission.")
                    except discord.errors.NotFound:
                        raise CancelCommand

                emoji = str(reaction)
                fn = reactions[emoji]
                x = fn()

                if x is not False:
                    i = x
                    await self.turn_page(i, pages)

                if user:
                    try:
                        await self.sent_message.remove_reaction(emoji, user)
                    except discord.errors.Forbidden:
                        raise Error("I'm missing the `Manage Messages` permission.")
                    except discord.errors.NotFound:
                        raise CancelCommand


        return self.sent_message