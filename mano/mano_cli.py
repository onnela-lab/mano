import logging
import sys
from copy import deepcopy
from os import name
from os.path import abspath
from sys import argv as command_line_args

from mano.constants import InternalError, logger as log, VALID_EXTENSIONS_ANDED
from mano.file_management import (check_is_valid_beiwe_data_file, compress_to_zst_files,
    decompress_zst_files, validate_is_a_folder_or_valid_beiwe_data_file,
    validate_is_a_folder_or_zst_file)


log.setLevel(logging.DEBUG)

# list of all commands
COMPRESS = "compress"
DECOMPRESS = "decompress"

# list all double-dashed parameters here
DELETE_ZST = "--delete-zst"
OVERWRITE = "--overwrite"
DELETE_ORIGINAL = "--delete-original"


PARAMETERS_BY_COMMAND = {
    DECOMPRESS: [DELETE_ZST, OVERWRITE],
    COMPRESS: [DELETE_ORIGINAL, OVERWRITE],
}

CLI_HELP_MESSAGE = f"""
mano currently supports 2 commands: decompress and compress.
  Parameters inside [brackets] are optional.
  <Parameters in angle brackets> are required.

~File Management~

"mano decompress <directory or file path> [{DELETE_ZST}] [{OVERWRITE}]"
  This command will decompress all .zst files in the specified directory.
  (You can specify the current directory with a single dot: `.`)

"mano compress <directory or file path> [-#] [{DELETE_ORIGINAL}] [{OVERWRITE}]"
  This command will compress all .zst files in the specified directory.
  You can optionally provide a `-#` (like `-8`) to set a compression level.
    (Default is 2, maximum is 22, gains can be up to about 30% smaller.
    High values get very, very slow.)


Global Options - you can always provide these with any command:
  add -y or --yes to skip all user interaction prompts.
"""  # retain final new line.


# Global settings should default to values as if they were NOT called from the CLI
# the main() function will set these values appropriately for CLI usage.
class GlobalSettings:
    skip_user_interaction: bool = True


def main():
    # reset global settings to default CLI values
    GlobalSettings.skip_user_interaction = False
    
    log.debug(f"mano received the following cli args: {sys.argv}")
    
    # (when main is called sys.argv[0] should always be the script's name.)
    # Display help on no args, -h, --help
    if len(sys.argv) < 2 or "-h" in sys.argv or "--help" in sys.argv:
        for line in CLI_HELP_MESSAGE.split("\n"):  # do not change to splitlines
            log.info(line)                         # we want blank lines retained
        return
    
    args = deepcopy(command_line_args[1:])
    
    # handle global parameters first, remove from args
    if "-y" in args or "--yes" in args:
        GlobalSettings.skip_user_interaction = True
        args.remove("-y") if "-y" in args else args.remove("--yes")
    
    the_command = args.pop(0)
    
    # dispatch to the appropriate command
    if the_command == DECOMPRESS:
        decompress(args)
    elif the_command == COMPRESS:
        compress(args)
    else:
        log.error(f"unknown command: `{args}`")
        exit(1)
    
    exit(0)


#
## "User Interface" helpers"
#


def confirm_command(*args: str):
    """
    Provide any number of strings describing exactly what is about to happen.
    The first parameter should be a general description, subsequent parameters
    should describe the state of every option/flag whether it was provided or not.
    """
    if GlobalSettings.skip_user_interaction:
        return
    
    for arg in args:
        if not isinstance(arg, str):  # type: ignore
            raise InternalError("confirm_command() only accepts string arguments")
    
    # display, confirm, exit or proceed.
    log.info("\nPlease confirm you want to:")
    for arg in args:
        log.info(f"\t- {arg}")
    
    response = input("(y/n): ").strip().lower()
    if response == "y" or response == "yes":  # don't get fancy, just y and yes
        log.info("proceeding...")
        return
    
    log.error("")  # blank line for readability
    log.error("Exiting mano, no actions were taken.")
    exit(0)


#
## Commands
#


def decompress(args: list[str]):
    ensure_minimum_number_of_args(DECOMPRESS, args, 1)
    ensure_only_allowed_parameters(DECOMPRESS, args, [DELETE_ZST, OVERWRITE], args[0])
    
    # file path must come before delete_zst and overwrite (index 0)
    target_path = args[0]
    delete_zst = DELETE_ZST in args
    overwrite = OVERWRITE in args
    
    validate_is_a_folder_or_zst_file(target_path)
    
    class info:
        describe = \
            f"Decompress all .zst files in the directory `{abspath(target_path)}` and its subdirectories."
        delete_zst = {
            True: "DELETE the .zst files after decompressing them",
            False: "RETAIN any .zst files after decompressing them"
        }
        overwrite = {
            True: "OVERWRITE any existing files",
            False: "SKIP any files that already exist"
        }
    if target_path.endswith('.zst'):
        info.describe = f"Decompress the .zst file `{abspath(target_path)}`"
        info.delete_zst = {
            True: "DELETE the .zst file when finished",
            False: "RETAIN the .zst file when finished"
        }
        info.overwrite = {
            True: "OVERWRITE the existing file",
            False: "SKIP it if a file already exists"
        }
    
    confirm_command(
        info.describe,
        info.delete_zst[delete_zst],
        info.overwrite[overwrite],
    )
    try:
        decompress_zst_files(target_path, delete_zsts=delete_zst, overwrite=overwrite)
    except Exception:
        # simple statement of what failed, details should be printed in the called functions.
        # TODO: improve logging of exceptions
        log.error("An error occurred while decompressing .zst files.")
        exit(2)


def compress(args: list[str]):
    ensure_minimum_number_of_args(COMPRESS, args, 1)
    compression_level = extract_compression_level(args)  # removes -# from args if present
    ensure_only_allowed_parameters(COMPRESS, args, [DELETE_ORIGINAL, OVERWRITE], args[0])
    
    # file path must come before delete_original and overwrite (index 0)
    target_path = args[0]
    delete_original = DELETE_ORIGINAL in args
    overwrite = OVERWRITE in args
    
    validate_is_a_folder_or_valid_beiwe_data_file(target_path)
    
    class info:
        compression_level: str  # (IDE complains incorrectly without this line)
        describe = \
            f"Compress all {VALID_EXTENSIONS_ANDED} files in the directory " \
                f"`{abspath(target_path)}` and its subdirectories."
        delete_original = {
            True: "DELETE the original files after compressing them",
            False: "RETAIN the original files after compressing them"
        }
        overwrite = {
            True: "OVERWRITE any existing .zst files",
            False: "SKIP any .zst files that already exist"
        }
    if check_is_valid_beiwe_data_file(target_path):
        info.describe = f"Compress the file `{abspath(target_path)}`"
        info.delete_original = {
                True: "DELETE the original file after compressing it",
                False: "RETAIN the original file after compressing it"
            }
        info.overwrite = {
                True: "OVERWRITE any existing .zst file",
                False: "SKIP if a .zst file already exists"
            }
    
    info.compression_level = f"using compression level {compression_level}"
    if compression_level == 2: # default
        info.compression_level += " (the default)"
    
    confirm_command(
        info.describe,
        info.delete_original[delete_original],
        info.overwrite[overwrite],
        info.compression_level,
    )
    
    try:
        compress_to_zst_files(
            target_path,
            delete_original=delete_original,
            overwrite=overwrite,
            compression_level=compression_level,
        )
    except Exception:
        # simple statement of what failed, details should be printed in the called functions.
        # TODO: improve logging of exceptions
        log.error("An error occurred while compressing zstd files.")
        exit(2)


def extract_compression_level(args: list[str]) -> int:
    """ look for a -# parameter in args, where # is an integer from 0 to 22. """
    level_str = "-2"  # default compression level
    for arg in args:
        # only digits after a single dash
        if arg.startswith('-') and len(arg) >= 2 and arg[1:].isdigit():
            level_str = arg
            args.remove(arg)  # remove from args only if found
            break
    
    # validate level between 0 and 22
    level = int(level_str[1:])
    if not (0 <= level <= 22):
        log.error(f"Invalid compression level `{level}` provided. Must be between 0 and 22.")
        exit(1)
    
    return level


#
# Validation
#


def ensure_minimum_number_of_args(
    command_name: str,
    args: list[str],
    minimum_required_argument_count_including_the_command_itself: int,
):
    # Display a useful error about missing arguments, then exit with a non-zero status.
    if len(args) < minimum_required_argument_count_including_the_command_itself:
        log.error(
            "\n"
            f"insufficient arguments, `{command_name}` expected at least "
            f"{minimum_required_argument_count_including_the_command_itself}, but got {len(args)}."
        )
        # log.error(f"\targs: {args}\n")
        exit(1)


def ensure_only_allowed_parameters(
    command_name: str, args: list[str], allowed_parameters: list[str], file_path_parameter: str|None = None
):
    """
    Currently a check for exact match of allowed parameters only.
    """
    # Display a useful error about _all_ unrecognized parameters, then exit with a non-zero status.
    any_bad_params = False
    for arg in args:
        if arg is file_path_parameter:
            continue
        if arg not in allowed_parameters:
            log.error(f"\nUnknown parameter `{arg}` provided to command `{command_name}`.\n")
            any_bad_params = True
            log.info("Allowed parameters are:")
            for param in sorted(PARAMETERS_BY_COMMAND[command_name]):
                log.info(f"\t{param}")
    
    if any_bad_params:
        exit(1)


if name == "__main__":
    raise NotImplementedError(
        "This file is not meant to be run directly. Please run 'mano' from the command line."
    )
