from ..structures.Bloxlink import Bloxlink # pylint: disable=import-error, no-name-in-module
from ..exceptions import CancelCommand # pylint: disable=import-error, no-name-in-module
from discord import User, Message


execute_interaction_command, send_autocomplete_options = Bloxlink.get_module("interactions", attrs=["execute_interaction_command", "send_autocomplete_options"])


@Bloxlink.event
async def on_interaction(interaction):
    data = interaction.data
    command_name = interaction.data.get("name")
    command_id   = interaction.data.get("id")
    command_args = {}

    first_response = interaction.response
    followups      = interaction.followup

    guild   = interaction.guild
    channel = interaction.channel
    user    = interaction.user

    if data.get("target_id"): # context menu command
        resolved = None

        if data.get("resolved"):
            if data["resolved"].get("users"):
                resolved = User(state=interaction._state, data=list(data["resolved"]["users"].values())[0])
            else:
                resolved = Message(state=interaction._state, channel=channel, data=list(data["resolved"]["messages"].values())[0])

        try:
            await execute_interaction_command("extensions", command_name, command_id, guild=guild, channel=channel, user=user,
                                              first_response=first_response, interaction=interaction, followups=followups,
                                              resolved=resolved
                                              )
        except CancelCommand:
            pass
    else: # slash command
        if not command_name:
            return

        subcommand = None
        focused_option = None

        if data.get("options"):
            for arg in data["options"]:
                if arg.get("options"):
                    subcommand = arg["name"]

                    for arg2 in arg["options"]:
                        if arg2.get("focused"):
                            focused_option = arg2

                        command_args[arg2["name"]] = arg2["value"]
                else:
                    if arg.get("value") is not None:
                        if arg.get("focused"):
                            focused_option = arg

                        command_args[arg["name"]] = arg["value"]
                    else:
                        subcommand = arg["name"]

        if not guild:
            return

        if focused_option:
            await send_autocomplete_options(interaction, command_name, subcommand, command_args, focused_option)
            return

        # execute slash command
        try:
            await execute_interaction_command("commands", command_name, guild=guild, channel=channel,
                                                user=user, first_response=first_response,
                                                interaction=interaction,
                                                followups=followups, command_id=command_id,
                                                subcommand=subcommand, arguments=command_args)
        except CancelCommand:
            pass
