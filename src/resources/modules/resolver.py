import discord
from re import compile

from ..structures.Bloxlink import Bloxlink # pylint: disable=import-error, no-name-in-module

import string


@Bloxlink.module
class Resolver(Bloxlink.Module):
    def __init__(self):
        self.user_pattern = compile(r"<@!?([0-9]+)>")
        self.role_pattern = compile(r"<@&([0-9]+)>")

    async def string_resolver(self, arg, message=None, guild=None, content=None, **kwargs):
        if message and not content:
            content = message.content

        min = arg.get("min", 1)
        max = arg.get("max", 100)

        if message and message.role_mentions:
            for role_mention in message.role_mentions:
                for role_match in self.role_pattern.finditer(content):
                    role_id = role_match.group(1)

                    if str(role_mention.id) == role_id:
                        content = content.replace(role_match.group(0), role_mention.name)

        if arg.get("min") or arg.get("max"):
            if min <= len(content) <= max:
                return str(content), None
            else:
                return False, f"String character count not in range: {min}-{max}"

        return str(content), None

    async def number_resolver(self, arg, message=None, guild=None, content=None, **kwargs):
        if message and not content:
            content = message.content

        if content.isdigit():
            min = arg.get("min", 1)
            max = arg.get("max", 100)

            int_content = int(content)

            if arg.get("min") or arg.get("max"):
                if min <= int_content <= max:
                    return int_content, None
                else:
                    return False, f'Number character count not in range: [{min}-{max}]'
            else:
                return int_content, None

        return False, "You must pass a number"

    async def choice_resolver(self, arg, message=None, guild=None, content=None, select_options=None):
        if message and not content:
            content = message.content

        if select_options:
            user_choices = select_options

            for i, user_choice in enumerate(user_choices):
                user_choices[i] = user_choice.lower()
        else:
            content = content.lower()
            content = content.strip(string.punctuation)
            user_choices = [content]

        choice_dict = {x:True for x in arg["choices"]}
        parsed_choices = []

        for user_choice in user_choices:
            if user_choice in choice_dict:
                parsed_choices.append(user_choice)
                continue

            for choice in arg["choices"]:
                choice_lower = choice.lower()

                if choice_lower == user_choice or user_choice == choice_lower[0:len(user_choice)]:
                    parsed_choices.append(choice)

        if parsed_choices:
            if select_options or arg.get("components"):
                return parsed_choices, None
            else:
                return parsed_choices[0], None

        return False, f"Choice must be of either: {str(arg['choices'])}"

    async def user_resolver(self, arg, message=None, guild=None, content=None, **kwargs):
        if message and not content:
            content = message.content

        if not arg.get("multiple"):
            if message:
                if message.raw_mentions:
                    user_id = self.user_pattern.search(content)

                    if user_id:
                        user_id = int(user_id.group(1))

                        if user_id != self.client.user.id:
                            try:
                                if guild and arg.get("guild_members_only"):
                                    user = guild.get_member(user_id) or await guild.fetch_member(user_id)
                                else:
                                    user = discord.utils.find(lambda u: u.id == user_id, message.mentions) or await self.client.fetch_user(user_id)

                                return user, None

                            except discord.errors.NotFound:
                                return False, "A user with this discord ID does not exist"

            is_int, is_id = None, None

            try:
                is_int = int(content)
                is_id = is_int > 15
            except ValueError:
                pass

            if is_id:
                user = guild and guild.get_member(is_int)

                if user:
                    return user, None
                else:
                    try:
                        if guild and arg.get("guild_members_only"):
                            user = guild.get_member(int(is_int)) or await guild.fetch_member(int(is_int))
                        else:
                            user = await self.client.fetch_user(int(is_int))

                        return user, None

                    except discord.errors.NotFound:
                        return False, "A user with this discord ID does not exist"
            else:
                member = guild and guild.get_member(content)

                if not member:
                    member = guild and await guild.query_members(content, limit=1)

                    if member:
                        return member[0], None
                    else:
                        return False, "Could not find a matching member. Please search by their username or ID."

            return False, "Invalid user"
        else:
            users = set()
            max = arg.get("max")
            count = 0

            lookup_strings = content.split(" ")

            if max:
                lookup_strings = lookup_strings[:max]

            if message and message.raw_mentions:
                for user_search in self.user_pattern.finditer(content):
                    if max:
                        if count >= max:
                            break
                        else:
                            count += 1

                    user = discord.utils.find(lambda u: u.id == int(user_search.group(1)), message.mentions)

                    if user:
                        users.add(user)

            for lookup_string in lookup_strings:
                if lookup_string:
                    if max:
                        if count >= max:
                            break

                    if lookup_string.isdigit():
                        try:
                            if guild and arg.get("guild_members_only"):
                                user = guild.get_member(int(lookup_string)) or await guild.fetch_member(int(lookup_string))
                            else:
                                user = await Bloxlink.fetch_user(int(lookup_string))
                        except discord.errors.NotFound:
                            pass
                        else:
                            users.add(user)

                    else:
                        member = guild and await guild.query_members(lookup_string, limit=1)

                        if member:
                            users.add(member[0])

                    count += 1

            if not users:
                return None, "Invalid user(s)"

            return list(users), None


    async def channel_resolver(self, arg, message=None, guild=None, content=None, **kwargs):
        if message and not content:
            content = message.content

        channels = []

        create_missing_channel = arg.get("create_missing_channel", True)
        allow_categories = arg.get("allow_categories", False)
        max = arg.get("max")
        multiple = arg.get("multiple")

        if allow_categories:
            lookup_channels = guild.text_channels + guild.categories
        else:
            lookup_channels = guild.text_channels

        if message and message.channel_mentions:
            for channel in message.channel_mentions:
                channels.append(channel)

                if not multiple:
                    break
        else:
            lookup_strings = content.split(",")

            for lookup_string in lookup_strings:
                if lookup_string:
                    lookup_string = lookup_string.strip()
                    channel = None

                    if lookup_string.isdigit():
                        channel = discord.utils.find(lambda c: c.id == int(lookup_string), lookup_channels)
                    else:
                        channel = discord.utils.find(lambda c: c.name == lookup_string, lookup_channels)

                    if not channel:
                        if create_missing_channel:
                            try:
                                channel = await guild.create_text_channel(name=lookup_string.replace(" ", "-"))
                            except discord.errors.Forbidden:
                                return None, "I was unable to create the channel. Please ensure I have the `Manage Channels` permission."
                            else:
                                channels.append(channel)
                        else:
                            return None, "Invalid channel"
                    else:
                        if channel not in channels:
                            channels.append(channel)

        if not channels:
            return None, "Invalid channel(s)"

        if max:
            return channels[:max], None
        else:
            if multiple:
                return channels, None
            else:
                return channels[0], None


    async def category_resolver(self, arg, message=None, guild=None, content=None, **kwargs):
        if message and not content:
            content = message.content

        categories = []
        create_missing_category = arg.get("create_missing_category", True)
        max = arg.get("max")
        multiple = arg.get("multiple")

        lookup_strings = content.split(",")

        for lookup_string in lookup_strings:
            if lookup_string:
                lookup_string = lookup_string.strip()
                category = None

                if lookup_string.isdigit():
                    category = discord.utils.find(lambda c: c.id == int(lookup_string), guild.categories)
                else:
                    category = discord.utils.find(lambda c: c.name == lookup_string, guild.categories)

                if not category:
                    if create_missing_category:
                        try:
                            category = await guild.create_category(name=lookup_string)
                        except discord.errors.Forbidden:
                            return None, "I was unable to create the category. Please ensure I have the `Manage Channels` permission."
                        else:
                            categories.append(category)
                    else:
                        return None, "Invalid category"
                else:
                    if category not in categories:
                        categories.append(category)

        if not categories:
            return None, "Invalid category"

        if max:
            return categories[:max], None
        else:
            if multiple:
                return categories, None
            else:
                return categories[0], None


    async def role_resolver(self, arg, message=None, guild=None, content=None, **kwargs):
        if message and not content:
            content = message.content

        roles = []
        create_missing_role = arg.get("create_missing_role", True)
        max = arg.get("max")
        multiple = arg.get("multiple")

        if message and message.role_mentions:
            for role in message.role_mentions:
                roles.append(role)

                if not multiple:
                    break
        else:
            lookup_strings = multiple and content.split(",") or [content]

            for lookup_string in lookup_strings:
                if lookup_string:
                    lookup_string = lookup_string.strip()
                    role = None

                    if lookup_string.isdigit():
                        role = guild.get_role(int(lookup_string))
                    else:
                        role = discord.utils.find(lambda r: r.name == lookup_string, guild.roles)

                    if not role:
                        if create_missing_role:
                            try:
                                role = await guild.create_role(name=lookup_string)
                            except discord.errors.Forbidden:
                                return None, "I was unable to create the role. Please ensure I have the `Manage Roles` permission."
                            else:
                                roles.append(role)
                        else:
                            return None, "Invalid role(s)"
                    else:
                        if role != guild.default_role and role not in roles:
                            roles.append(role)

        if not roles:
            return None, "Invalid role(s)"

        if max:
            return roles[:max], None
        else:
            if multiple:
                return roles, None
            else:
                return roles[0], None


    async def image_resolver(self, arg, message=None, guild=None, content=None, **kwargs):
        if message and not content:
            content = message.content

        if message and message.attachments:
            for attachment in message.attachments:
                if attachment.height and attachment.width:
                    # is an image
                    return attachment.proxy_url or attachment.url, None

        if "https://" in content:
            return content, None
        else:
            return False, "This doesn't appear to be a valid https URL."


    async def list_resolver(self, arg, message=None, guild=None, content=None, **kwargs):
        if message and not content:
            content = message.content

        max = arg.get("max")

        items = content.split(",")
        items = [x.strip() for x in items]

        if max:
            return items[:max], None
        else:
            return items, None


    def get_resolver(self, name):
        for method_name in dir(self):
            if method_name.endswith("resolver") and name in method_name:
                if callable(getattr(self, method_name)):
                    return getattr(self, method_name)

