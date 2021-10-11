from discord import Embed
import discord
from ..structures.Bloxlink import Bloxlink # pylint: disable=import-error, no-name-in-module
from ..exceptions import CancelledPrompt, CancelCommand, Error # pylint: disable=import-error, no-name-in-module
from ..constants import RED_COLOR, INVISIBLE_COLOR # pylint: disable=import-error, no-name-in-module
from config import RELEASE # pylint: disable=no-name-in-module, import-error
from ..constants import IS_DOCKER, TIP_CHANCES, SERVER_INVITE, PROMPT # pylint: disable=import-error, no-name-in-module
import random
import asyncio

get_resolver = Bloxlink.get_module("resolver", attrs="get_resolver")
broadcast = Bloxlink.get_module("ipc", attrs="broadcast")
suppress_timeout_errors = Bloxlink.get_module("utils", attrs="suppress_timeout_errors")

active_prompts = {}


class Arguments:
    def __init__(self, CommandArgs, author, channel, command, guild=None, message=None, subcommand=None, slash_command=None):
        self.channel = channel
        self.author  = author
        self.message = message
        self.guild   = guild

        self.command    = command
        self.subcommand = subcommand

        self.command_args = CommandArgs
        self.response     = CommandArgs.response
        self.locale       = CommandArgs.locale
        self.prefix       = CommandArgs.prefix

        self.messages  = []
        self.dm_post   = None
        self.cancelled = False
        self.dm_false_override = False
        self.first_slash = True
        self.skipped_args = []

        self.slash_command = slash_command

        self.parsed_args = {}

    async def initial_command_args(self, text_after=""):
        if self.subcommand:
            prompts = self.subcommand[1].get("arguments")
        else:
            if self.slash_command:
                prompts = self.command.slash_args or self.command.arguments
            else:
                prompts = self.command.arguments

        if self.slash_command:
            self.parsed_args = await self.prompt(prompts, is_base_slash_command=True) if prompts else {}
            self.command_args.add(parsed_args=self.parsed_args, string_args=[])

            return

        arg_len = len(prompts) if prompts else 0
        skipped_args = []
        split = text_after.split(" ")
        temp = []

        for arg in split:
            if arg:
                if arg.startswith('"') and arg.endswith('"'):
                    arg = arg.replace('"', "")

                if len(skipped_args) + 1 == arg_len:
                    t = text_after.replace('"', "")
                    toremove = " ".join(skipped_args)

                    if t.startswith(toremove):
                        t = t[len(toremove):]

                    t = t.strip()

                    skipped_args.append(t)

                    break

                if arg.startswith('"') or (temp and not arg.endswith('"')):
                    temp.append(arg.replace('"', ""))

                elif arg.endswith('"'):
                    temp.append(arg.replace('"', ""))
                    skipped_args.append(" ".join(temp))
                    temp.clear()

                else:
                    skipped_args.append(arg)

        if len(skipped_args) > 1:
            self.skipped_args = skipped_args
        else:
            if text_after:
                self.skipped_args = [text_after]
            else:
                self.skipped_args = []

        if prompts:
            self.parsed_args = await self.prompt(prompts)

        self.command_args.add(parsed_args=self.parsed_args, string_args=text_after and text_after.split(" ") or [])


    async def say(self, text, type=None, footer=None, embed_title=None, is_prompt=True, embed_color=INVISIBLE_COLOR, embed=True, dm=False, components=None):
        embed_color = embed_color or INVISIBLE_COLOR
        view = discord.ui.View(timeout=PROMPT["PROMPT_TIMEOUT"])

        if components:
            for component in components:
                if isinstance(component, discord.ui.Button):
                    component.custom_id = component.label

                view.add_item(item=component)

        if type != "error":
            view.add_item(item=discord.ui.Button(style=discord.ButtonStyle.secondary, label="Cancel", custom_id="cancel"))

        if self.dm_false_override:
            dm = False

        if footer:
            footer = f"{footer}\n"
        else:
            footer = ""

        if not embed:
            if is_prompt:
                text = f"{text}\n\n{footer}\n{self.locale('prompt.timeoutWarning', timeout=PROMPT['PROMPT_TIMEOUT'])}"

            return await self.response.send(text, dm=dm, no_dm_post=True, strict_post=True, view=view)

        description = f"{text}\n\n{footer}"

        if type == "error":
            new_embed = Embed(title=embed_title or self.locale("prompt.errors.title"))
            new_embed.colour = RED_COLOR

            show_help_tip = random.randint(1, 100)

            if show_help_tip <= TIP_CHANCES["PROMPT_ERROR"]:
                description = f"{description}\n\nExperiencing issues? Our [Support Server]({SERVER_INVITE}) has a team of Helpers ready to help you if you're having trouble!"
        else:
            new_embed = Embed(title=embed_title or self.locale("prompt.title"))
            new_embed.colour = embed_color

        new_embed.description = description

        new_embed.set_footer(text=self.locale("prompt.timeoutWarning", timeout=PROMPT["PROMPT_TIMEOUT"]))

        msg = await self.response.send(embed=new_embed, dm=dm, no_dm_post=True, strict_post=True, ignore_errors=True, view=view)

        if not msg:
            if is_prompt:
                text = f"{text}\n\n{self.locale('prompt.toCancel')}\n\n{self.locale('prompt.timeoutWarning', timeout=PROMPT['PROMPT_TIMEOUT'])}"

            return await self.response.send(text, dm=dm, no_dm_post=True, strict_post=True, view=view)

        if msg and not dm:
            if self.slash_command and self.first_slash:
                self.first_slash = False
                return msg

            self.messages.append(msg.id)

        return msg


    @staticmethod
    def in_prompt(author):
        return active_prompts.get(author.id)

    async def prompt(self, prompts, error=False, dm=False, no_dm_post=False, is_base_slash_command=False, last=False):
        active_prompts[self.author.id] = True

        resolved_arg_count = 0
        prompt_groups = {}
        resolved_args = {}
        last_prompt = None
        err_count = 0
        optional_arg_has_arg = False

        if dm and IS_DOCKER:
            try:
                m = await self.author.send("Loading setup...")
            except discord.errors.Forbidden:
                dm = False
            else:
                try:
                    await m.delete()
                except discord.errors.NotFound:
                    pass

                if not no_dm_post:
                    self.dm_post = await self.response.send(f"{self.author.mention}, **please check your DMs to continue.**", ignore_errors=True, strict_post=True)

        if is_base_slash_command:
            for i, prompt in enumerate(prompts): # to make easy O(1) lookup to get the position to append the arg in
                prompt_groups[prompt["name"]] = i

        try:
            while resolved_arg_count != len(prompts):
                if err_count == PROMPT["PROMPT_ERROR_COUNT"]:
                    raise CancelledPrompt("Too many failed attempts.", type="delete")

                if last and resolved_arg_count +1 == len(prompts):
                    self.skipped_args = [" ".join(self.skipped_args)]

                current_input = None
                drop_skipped_arg = False
                message     = None
                interaction = None
                select_values = []
                custom_id = None

                current_prompt = prompts[resolved_arg_count]
                prompt_text = current_prompt["prompt"]

                if is_base_slash_command and self.slash_command.get(current_prompt["name"]):
                    current_input = self.slash_command.get(current_prompt["name"])
                else:
                    current_input = str(self.skipped_args[0]) if self.skipped_args else ""

                    if current_input:
                        drop_skipped_arg = True

                if current_prompt.get("optional") and current_input:
                    optional_arg_has_arg = True

                if not current_input and not optional_arg_has_arg and (current_prompt.get("optional") or (is_base_slash_command and current_prompt.get("slash_optional"))) or (current_prompt.get("show_if") and last_prompt and current_prompt["name"] != last_prompt["name"] and not current_prompt["show_if"](resolved_args)): # check if they supplied an arg, otherwise skip this prompt
                    resolved_args[current_prompt["name"]] = None
                    resolved_arg_count += 1

                    if drop_skipped_arg:
                        self.skipped_args.pop(0)

                    continue

                current_input = str(current_input) if current_input else ""

                if not current_input:
                    try:
                        if current_prompt.get("formatting", True):
                            prompt_text = prompt_text.format(**resolved_args, prefix=self.prefix)

                        bot_prompt = await self.say(prompt_text, embed_title=current_prompt.get("embed_title"), embed_color=current_prompt.get("embed_color"), footer=current_prompt.get("footer"), type=error and "error", embed=True, dm=dm, components=current_prompt.get("components", []))

                        if dm and IS_DOCKER:
                            message_data = (await broadcast(self.author.id, type="DM_AND_INTERACTION", send_to=f"{RELEASE}:CLUSTER_0", waiting_for=1, timeout=PROMPT["PROMPT_TIMEOUT"]+50))[0]

                            if not message_data:
                                await self.say("Cluster which handles DMs is temporarily unavailable. Please say your message in the server instead of DMs.", type="error", embed=True, dm=dm)
                                self.dm_false_override = True
                                dm = False

                                message = await Bloxlink.wait_for("message", check=self._check_prompt(), timeout=PROMPT["PROMPT_TIMEOUT"])
                                current_input = message.content

                                if current_prompt.get("delete_original", True):
                                    self.messages.append(message.id)
                            else:
                                if message_data != "cluster timeout":
                                    message_type = message_data.get("type")

                                    if message_type in ("message", "button"):
                                        current_input = message_data["content"]

                                    elif message_type == "select":
                                        select_values = message_data["values"]

                            if message_data == "cluster timeout":
                                current_input = "cancel (timeout)"

                        else:
                            task_1 = asyncio.create_task(suppress_timeout_errors(Bloxlink.wait_for("message", check=self._check_prompt(dm), timeout=PROMPT["PROMPT_TIMEOUT"])))
                            task_2 = asyncio.create_task(suppress_timeout_errors(Bloxlink.wait_for("interaction", check=self._check_interaction(), timeout=PROMPT["PROMPT_TIMEOUT"])))

                            result_set, pending = await asyncio.wait({task_1, task_2}, return_when=asyncio.FIRST_COMPLETED, timeout=PROMPT["PROMPT_TIMEOUT"])

                            if not result_set:
                                raise CancelledPrompt(f"timeout ({PROMPT['PROMPT_TIMEOUT']}s)", dm=dm)

                            result = next(iter(result_set)).result()

                            if isinstance(result, discord.Interaction):
                                interaction = result
                                message = None
                                custom_id = interaction.data["custom_id"]

                                if interaction.data["component_type"] == 3:
                                    select_values = interaction.data["values"]
                                # TODO: get interaction key and use that for the next response
                            else:
                                interaction = None
                                message = result

                            if message:
                                current_input = message.content

                                if current_prompt.get("delete_original", True):
                                    self.messages.append(message.id)
                            else:
                                current_input = custom_id

                        current_input_lower = current_input.lower() if current_input else None

                        if bot_prompt and bot_prompt.components:
                            disabled_view = discord.ui.View.from_message(bot_prompt)

                            for child in disabled_view.children:
                                if hasattr(child, "disabled"):
                                    child.disabled = True

                            try:
                                await bot_prompt.edit(view=disabled_view)
                            except discord.errors.NotFound:
                                pass

                        if custom_id == "cancel":
                            raise CancelledPrompt(type="delete")
                        elif current_input_lower == "cancel":
                            raise CancelledPrompt(type="delete", dm=dm)
                        elif current_input_lower == "cancel (timeout)":
                            raise CancelledPrompt(f"timeout ({PROMPT['PROMPT_TIMEOUT']}s)", dm=dm)

                    except asyncio.TimeoutError:
                        raise CancelledPrompt(f"timeout ({PROMPT['PROMPT_TIMEOUT']}s)", dm=dm)

                skipped_arg_lower = str(current_input).lower()

                if skipped_arg_lower in current_prompt.get("exceptions", []):
                    resolved_arg_count += 1
                    resolved_args[current_prompt["name"]] = skipped_arg_lower
                    optional_arg_has_arg = False
                    last_prompt = current_prompt

                    if drop_skipped_arg:
                        self.skipped_args.pop(0)

                    continue

                resolver_types = current_prompt.get("type", "string")

                if not isinstance(resolver_types, list):
                    resolver_types = [resolver_types]

                resolve_errors = []
                resolved = False
                error_message = None

                for resolver_type in resolver_types:
                    resolver = get_resolver(resolver_type)
                    resolved, error_message = await resolver(current_prompt, content=str(current_input), guild=self.guild, message=message or self.message, select_options=select_values)

                    if resolved:
                        if current_prompt.get("validation"):
                            res = [await current_prompt["validation"](content=str(current_input), message=not dm and message, prompt=self.prompt, guild=self.guild)]

                            if isinstance(res[0], tuple):
                                if not res[0][0]:
                                    error_message = res[0][1]
                                    resolved = False
                            else:
                                if not res[0]:
                                    error_message = "Prompt failed validation. Please try again."
                                    resolved = False

                            if resolved:
                                resolved = res[0]
                    else:
                        error_message = f"{self.locale('prompt.errors.invalidArgument', arg='**' + resolver_type + '**')}: `{error_message}`"

                    if error_message:
                        resolve_errors.append(error_message)
                    else:
                        break

                if resolved:
                    resolved_arg_count += 1
                    resolved_args[current_prompt["name"]] = resolved
                    optional_arg_has_arg = False
                else:
                    await self.say("\n".join(resolve_errors), type="error", embed=True, dm=dm)

                    if drop_skipped_arg:
                        self.skipped_args.pop(0)

                    err_count += 1

                if self.skipped_args:
                    self.skipped_args.pop(0)

                last_prompt = current_prompt

            return resolved_args

        finally:
            active_prompts.pop(self.author.id, None)

    def _check_prompt(self, dm=False):
        def wrapper(message):
            if message.author.id  == self.author.id:
                if dm:
                    return not message.guild
                else:
                    return message.channel.id == self.channel.id
            else:
                return False

        return wrapper

    def _check_interaction(self):
        def wrapper(interaction):
            if interaction.user.id == self.author.id and interaction.data.get("custom_id"):
                return True

        return wrapper
