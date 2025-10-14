import cli_ui
import glob
import json
import os
import re
import sys

from src.cleanup import cleanup, reset_terminal
from src.console import console
from src.exportmi import mi_resolution

try:
    from data.config import config  # type: ignore
except Exception:  # pragma: no cover - fallback for tests without a config module
    config = {  # type: ignore[assignment]
        "DEFAULT": {},
        "NAMING": {},
    }


async def get_uhd(type, guess, resolution, path):
    try:
        source = guess['Source']
        other = guess['Other']
    except Exception:
        source = ""
        other = ""
    uhd = ""
    if source == 'Blu-ray' and other == "Ultra HD" or source == "Ultra HD Blu-ray":
        uhd = "UHD"
    elif "UHD" in path:
        uhd = "UHD"
    elif type in ("DISC", "REMUX", "ENCODE", "WEBRIP"):
        uhd = ""

    if type in ("DISC", "REMUX", "ENCODE") and resolution == "2160p":
        uhd = "UHD"

    return uhd


async def get_hdr(mi, bdinfo):
    hdr = ""
    dv = ""
    if bdinfo is not None:  # Disks
        hdr_mi = bdinfo['video'][0]['hdr_dv']
        if "HDR10+" in hdr_mi:
            hdr = "HDR10+"
        elif hdr_mi == "HDR10":
            hdr = "HDR"
        try:
            if bdinfo['video'][1]['hdr_dv'] == "Dolby Vision":
                dv = "DV"
        except Exception:
            pass
    else:
        video_track = mi['media']['track'][1]
        try:
            hdr_mi = video_track['colour_primaries']
            if hdr_mi in ("BT.2020", "REC.2020"):
                hdr = ""
                hdr_fields = [
                    video_track.get('HDR_Format_Compatibility', ''),
                    video_track.get('HDR_Format_String', ''),
                    video_track.get('HDR_Format', '')
                ]
                hdr_format_string = next((v for v in hdr_fields if isinstance(v, str) and v.strip()), "")
                if "HDR10+" in hdr_format_string:
                    hdr = "HDR10+"
                elif "HDR10" in hdr_format_string:
                    hdr = "HDR"
                elif "SMPTE ST 2094 App 4" in hdr_format_string:
                    hdr = "HDR"
                if hdr_format_string and "HLG" in hdr_format_string:
                    hdr = f"{hdr} HLG"
                if hdr_format_string == "" and "PQ" in (video_track.get('transfer_characteristics'), video_track.get('transfer_characteristics_Original', None)):
                    hdr = "PQ10"
                transfer_characteristics = video_track.get('transfer_characteristics_Original', None)
                if "HLG" in transfer_characteristics:
                    hdr = "HLG"
                if hdr != "HLG" and "BT.2020 (10-bit)" in transfer_characteristics:
                    hdr = "WCG"
        except Exception:
            pass

        try:
            if "Dolby Vision" in video_track.get('HDR_Format', '') or "Dolby Vision" in video_track.get('HDR_Format_String', ''):
                dv = "DV"
        except Exception:
            pass

    hdr = f"{dv} {hdr}".strip()
    return hdr


async def get_video_codec(bdinfo):
    codecs = {
        "MPEG-2 Video": "MPEG-2",
        "MPEG-4 AVC Video": "AVC",
        "MPEG-H HEVC Video": "HEVC",
        "VC-1 Video": "VC-1"
    }
    codec = codecs.get(bdinfo['video'][0]['codec'], "")
    return codec


async def get_video_encode(mi, type, bdinfo):
    video_encode = ""
    codec = ""
    bit_depth = '0'
    has_encode_settings = False
    try:
        format = mi['media']['track'][1]['Format']
        format_profile = mi['media']['track'][1].get('Format_Profile', format)
        if mi['media']['track'][1].get('Encoded_Library_Settings', None):
            has_encode_settings = True
        bit_depth = mi['media']['track'][1].get('BitDepth', '0')
        encoded_library_name = mi['media']['track'][1].get('Encoded_Library_Name', None)
    except Exception:
        format = bdinfo['video'][0]['codec']
        format_profile = bdinfo['video'][0]['profile']
    if type in ("ENCODE", "WEBRIP", "DVDRIP"):  # ENCODE or WEBRIP or DVDRIP
        if format == 'AVC':
            codec = 'x264'
        elif format == 'HEVC':
            codec = 'x265'
        elif format == 'AV1':
            codec = 'AV1'
        elif format == 'MPEG-4 Visual':
            if encoded_library_name:
                if 'xvid' in encoded_library_name.lower():
                    codec = 'XviD'
                elif 'divx' in encoded_library_name.lower():
                    codec = 'DivX'
    elif type in ('WEBDL', 'HDTV'):  # WEB-DL
        if format == 'AVC':
            codec = 'H.264'
        elif format == 'HEVC':
            codec = 'H.265'
        elif format == 'AV1':
            codec = 'AV1'

        if type == 'HDTV' and has_encode_settings is True:
            codec = codec.replace('H.', 'x')
    elif format == "VP9":
        codec = "VP9"
    elif format == "VC-1":
        codec = "VC-1"
    if format_profile == 'High 10':
        profile = "Hi10P"
    else:
        profile = ""
    video_encode = f"{profile} {codec}"
    video_codec = format
    if video_codec == "MPEG Video":
        video_codec = f"MPEG-{mi['media']['track'][1].get('Format_Version')}"
    return video_encode, video_codec, has_encode_settings, bit_depth


async def get_video(videoloc, mode, sorted_filelist=False):
    filelist = []
    videoloc = os.path.abspath(videoloc)
    if os.path.isdir(videoloc):
        globlist = glob.glob1(videoloc, "*.mkv") + glob.glob1(videoloc, "*.mp4") + glob.glob1(videoloc, "*.ts")
        for file in globlist:
            if not file.lower().endswith('sample.mkv') or "!sample" in file.lower():
                full_path = os.path.abspath(f"{videoloc}{os.sep}{file}")
                filelist.append(full_path)
                filelist = sorted(filelist)
                if len(filelist) > 1:
                    for f in filelist:
                        if "sample" in os.path.basename(f).lower():
                            console.print("[green]Filelist:[/green]")
                            for tf in filelist:
                                console.print(f"[cyan]{tf}")
                            console.print(f"[bold red]Possible sample file detected in filelist!: [yellow]{f}")
                            try:
                                if cli_ui.ask_yes_no("Do you want to remove it?", default="yes"):
                                    filelist.remove(f)
                            except EOFError:
                                console.print("\n[red]Exiting on user request (Ctrl+C)[/red]")
                                await cleanup()
                                reset_terminal()
                                sys.exit(1)
                if any(tag in file for tag in ['{tmdb-', '{imdb-', '{tvdb-']):
                    console.print(f"[bold red]This looks like some *arr renamed file which is not allowed: [yellow]{file}")
                    default_section = config.get("DEFAULT", {})  # type: ignore[assignment]
                    naming_section = config.get("NAMING", {})  # type: ignore[assignment]
                    use_radarr = bool(default_section.get("use_radarr", False)) if isinstance(default_section, dict) else False
                    prefer_scene = bool(naming_section.get("prefer_radarr_scene_name", False)) if isinstance(naming_section, dict) else False
                    if use_radarr:
                        if prefer_scene:
                            console.print(
                                "[bold yellow]Radarr support is enabled—Upload Assistant will pull the scene name automatically later in the run.[/bold yellow]"
                            )
                        else:
                            console.print(
                                "[bold yellow]Radarr is enabled. Set NAMING.prefer_radarr_scene_name = True in your config to have Upload Assistant apply the Radarr scene name automatically.[/bold yellow]"
                            )
                    else:
                        console.print(
                            "[bold yellow]Tip: Enable use_radarr and NAMING.prefer_radarr_scene_name in data/config.py so Upload Assistant can look up the original scene name for you.[/bold yellow]"
                        )
                    console.print(
                        "[bold yellow]Choose 'no' if you want to stop and fix the filename before continuing.[/bold yellow]"
                    )
                    try:
                        if cli_ui.ask_yes_no("Do you want to upload with this file?", default="yes"):
                            pass
                        else:
                            new_path = await prompt_filename_correction(full_path)
                            if new_path:
                                try:
                                    original_index = filelist.index(full_path)
                                except ValueError:
                                    original_index = -1
                                if original_index >= 0:
                                    filelist[original_index] = new_path
                                else:
                                    filelist.append(new_path)
                                file = os.path.basename(new_path)
                    except EOFError:
                        console.print("\n[red]Exiting on user request (Ctrl+C)[/red]")
                        await cleanup()
                        reset_terminal()
                        sys.exit(1)
        try:
            if sorted_filelist:
                video = sorted(filelist, key=os.path.getsize, reverse=True)[0]
            else:
                video = sorted(filelist)[0]
        except IndexError:
            console.print("[bold red]No Video files found")
            if mode == 'cli':
                exit()
    else:
        video = videoloc
        filelist.append(videoloc)
    if sorted_filelist:
        filelist = sorted(filelist, key=os.path.getsize, reverse=True)
    else:
        filelist = sorted(filelist)
    return video, filelist


async def prompt_filename_correction(full_path: str) -> str | None:
    """Prompt the user for a replacement filename and apply it on disk.

    Returns the new absolute path when the rename succeeds, otherwise ``None``.
    """

    directory = os.path.dirname(full_path)
    original_name = os.path.basename(full_path)

    while True:
        try:
            new_name = cli_ui.ask_string(
                "Enter a new filename (leave blank to skip renaming):",
                default=original_name,
            )
        except EOFError:
            console.print("\n[red]Exiting on user request (Ctrl+C)[/red]")
            await cleanup()
            reset_terminal()
            sys.exit(1)

        if not new_name:
            console.print("[yellow]Skipping filename change and continuing with the existing file.[/yellow]")
            return None

        candidate = new_name.strip()
        if not candidate:
            console.print("[yellow]Skipping filename change and continuing with the existing file.[/yellow]")
            return None

        if os.path.sep in candidate or candidate in {".", ".."}:
            console.print("[bold red]Invalid filename. Please enter a name without path separators.[/bold red]")
            continue

        _, ext = os.path.splitext(original_name)
        if ext and not candidate.lower().endswith(ext.lower()):
            candidate = f"{candidate}{ext}"

        new_path = os.path.join(directory, candidate)

        if os.path.exists(new_path):
            console.print(f"[bold red]A file named [yellow]{candidate}[/yellow] already exists. Please choose another name.[/bold red]")
            continue

        try:
            os.rename(full_path, new_path)
        except OSError as exc:
            console.print(f"[bold red]Failed to rename file: {exc}[/bold red]")
            continue

        console.print(f"[green]Renamed file to: [yellow]{candidate}[/yellow][/green]")
        return os.path.abspath(new_path)


async def get_resolution(guess, folder_id, base_dir):
    hfr = False
    with open(f'{base_dir}/tmp/{folder_id}/MediaInfo.json', 'r', encoding='utf-8') as f:
        mi = json.load(f)
        try:
            width = mi['media']['track'][1]['Width']
            height = mi['media']['track'][1]['Height']
        except Exception:
            width = 0
            height = 0

        framerate = mi['media']['track'][1].get('FrameRate')
        if not framerate or framerate == '0':
            framerate = mi['media']['track'][1].get('FrameRate_Original')
        if not framerate or framerate == '0':
            framerate = mi['media']['track'][1].get('FrameRate_Num')
        if framerate:
            try:
                if int(float(framerate)) > 30:
                    hfr = True
            except Exception:
                hfr = False
        else:
            framerate = "24.000"

        try:
            scan = mi['media']['track'][1]['ScanType']
        except Exception:
            scan = "Progressive"
        if scan == "Progressive":
            scan = "p"
        elif scan == "Interlaced":
            scan = 'i'
        elif framerate == "25.000":
            scan = "p"
        else:
            # Fallback using regex on meta['uuid'] - mainly for HUNO fun and games.
            match = re.search(r'\b(1080p|720p|2160p|576p|480p)\b', folder_id, re.IGNORECASE)
            if match:
                scan = "p"  # Assume progressive based on common resolution markers
            else:
                scan = "i"  # Default to interlaced if no indicators are found
        width_list = [3840, 2560, 1920, 1280, 1024, 854, 720, 15360, 7680, 0]
        height_list = [2160, 1440, 1080, 720, 576, 540, 480, 8640, 4320, 0]
        width = await closest(width_list, int(width))
        actual_height = int(height)
        height = await closest(height_list, int(height))
        res = f"{width}x{height}{scan}"
        resolution = await mi_resolution(res, guess, width, scan, height, actual_height)
    return resolution, hfr


async def closest(lst, K):
    # Get closest, but not over
    lst = sorted(lst)
    mi_input = K
    res = 0
    for each in lst:
        if mi_input > each:
            pass
        else:
            res = each
            break
    return res


async def get_type(video, scene, is_disc, meta):
    if meta.get('manual_type'):
        type = meta.get('manual_type')
    else:
        filename = os.path.basename(video).lower()
        if "remux" in filename:
            type = "REMUX"
        elif any(word in filename for word in [" web ", ".web.", "web-dl", "webdl"]):
            type = "WEBDL"
        elif "webrip" in filename:
            type = "WEBRIP"
        # elif scene == True:
            # type = "ENCODE"
        elif "hdtv" in filename:
            type = "HDTV"
        elif is_disc is not None:
            type = "DISC"
        elif "dvdrip" in filename:
            type = "DVDRIP"
            # exit()
        else:
            type = "ENCODE"
    return type


async def is_3d(mi, bdinfo):
    if bdinfo is not None:
        if bdinfo['video'][0]['3d'] != "":
            return "3D"
        else:
            return ""
    else:
        return ""


async def is_sd(resolution):
    if resolution in ("480i", "480p", "576i", "576p", "540p"):
        sd = 1
    else:
        sd = 0
    return sd


async def get_video_duration(meta):
    if not meta.get('is_disc') == "BDMV" and meta.get('mediainfo', {}).get('media', {}).get('track'):
        general_track = next((track for track in meta['mediainfo']['media']['track']
                              if track.get('@type') == 'General'), None)

        if general_track and general_track.get('Duration'):
            try:
                media_duration_seconds = float(general_track['Duration'])
                formatted_duration = int(media_duration_seconds // 60)
                return formatted_duration
            except ValueError:
                if meta['debug']:
                    console.print(f"[red]Invalid duration value: {general_track['Duration']}[/red]")
                return None
        else:
            if meta['debug']:
                console.print("[red]No valid duration found in MediaInfo General track[/red]")
            return None
    else:
        return None


async def get_container(meta):
    if meta.get('is_disc', '') == 'BDMV':
        return 'm2ts'
    elif meta.get('is_disc', '') == 'HDDVD':
        return 'evo'
    elif meta.get('is_disc', '') == 'DVD':
        return 'vob'
    else:
        file_list = meta.get('filelist', [])

        if not file_list:
            console.print("[red]No files found to determine container[/red]")
            return ''

        try:
            largest_file_path = max(file_list, key=os.path.getsize)
        except (OSError, ValueError) as e:
            console.print(f"[red]Error getting container for file: {e}[/red]")
            return ''

        extension = os.path.splitext(largest_file_path)[1]
        return extension.lstrip('.').lower() if extension else ''
