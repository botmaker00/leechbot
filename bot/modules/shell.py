import html
import time
from io import BytesIO

from bot import LOGGER
from bot.helper.ext_utils.bot_utils import cmd_exec, new_task
from bot.helper.telegram_helper.message_utils import send_file, send_message


@new_task
async def run_shell(_, message):
    cmd = message.text.split(maxsplit=1)
    if len(cmd) == 1:
        await send_message(message, "No command to execute was given.")
        return
    cmd = cmd[1]

    # Format the input - escape HTML special characters
    safe_cmd = html.escape(cmd)
    formatted_input = f"<b>Input</b> -\n<pre>{safe_cmd}</pre>\n\n"

    # Execute the command and measure time
    start_time = time.time()
    stdout, stderr, _ = await cmd_exec(cmd, shell=True)
    execution_time = time.time() - start_time

    # Format the output - escape HTML special characters
    output = ""
    if len(stdout) != 0:
        output += f"{stdout}"
        LOGGER.info(f"Shell - {cmd} - {stdout}")
    if len(stderr) != 0:
        if output:
            output += f"\n\n{stderr}"
        else:
            output += f"{stderr}"
        LOGGER.warning(f"Shell - {cmd} - {stderr}")

    # Format the complete reply
    if output:
        safe_output = html.escape(output)
        formatted_output = f"<b>Output</b> -\n<pre>{safe_output}</pre>"
    else:
        formatted_output = "<b>Output</b> -\n<pre>No output</pre>"

    # Add execution time
    time_taken = f"<b>Time</b>: {execution_time:.2f}s"

    # Combine all parts
    reply = f"{formatted_input}{formatted_output}\n\n{time_taken}"

    # Send the response
    if len(reply) > 3000:
        with BytesIO(str.encode(reply)) as out_file:
            out_file.name = "shell_output.txt"
            await send_file(message, out_file)
    elif len(reply) != 0:
        await send_message(message, reply)
    else:
        await send_message(message, "No Reply")
