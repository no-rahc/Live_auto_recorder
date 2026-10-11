"""One side-effect-free validation boundary for settings saves and restores.

Callers must obtain acknowledgement from the live request, never from an imported
file. Omitted settings (including credentials) retain their current values.
"""
from __future__ import annotations

import os
import ntpath
import re
from typing import Any


class ConfigValidationError(ValueError):
    pass


BOOL_FIELDS = frozenset('''telegram_enabled discord_enabled autoRecordingMode
    autoPostProcessing deleteAfterPostProcessing removeFixedPrefix
    moveAfterProcessingEnabled postNewWindow splitRecordingMode splitPostProcessing
    stream_copy use_bitrate_mode loginMode enableTray minimizeToTrayOnClose
    minimizeToTrayOnStart fileManagerEnabled fileManagerReadOnly trashEnabled'''.split())
INT_RANGES = {
    'port': (1, 65535), 'recheckInterval': (1, 86400),
    'autoStopInterval': (0, 2147483647), 'splitOverlapSec': (0, 30),
    'timemachine_time_shift': (0, 3600), 'video_quality': (0, 63),
}
STRING_FIELDS = frozenset('''filenamePattern moveAfterProcessing video_codec preset
    video_bitrate vbv_maxrate vbv_bufsize extra_ffmpeg_options audio_codec
    audio_bitrate discord_webhook_url'''.split())
HELPER_FIELDS = frozenset('''danger_ack danger_confirmation danger_current_password
    telegram_bot_token telegram_chat_id telegram_bot_token_action
    telegram_chat_id_action discord_webhook_url_action'''.split())
DANGER_ACK = '위험 설정 적용'


def parse_bool(value: Any, field: str) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (str, int)) and str(value).strip().lower() in {'true', '1', 'on', 'yes', 'false', '0', 'off', 'no'}:
        return str(value).strip().lower() in {'true', '1', 'on', 'yes'}
    raise ConfigValidationError(f'{field}: true/false 값을 입력하세요.')


def normalize_roots(value: Any, *, require_existing: bool = False, enforce_policy: bool = True) -> list[str]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ConfigValidationError('fileManagerRoots: 경로 문자열 목록이 필요합니다.')
    result = []
    for item in value:
        item = item.strip()
        if not item:
            continue
        if '\x00' in item:
            raise ConfigValidationError('fileManagerRoots: 잘못된 경로입니다.')
        expanded = os.path.expanduser(item)
        if os.name == "nt":
            expanded = os.path.realpath(expanded)
        # Preserve the original form's protected-root exclusions across all
        # entry points, including symlink aliases and Windows drive roots.
        windows = bool(ntpath.splitdrive(expanded)[0])
        if windows:
            normalized = ntpath.normpath(expanded)
            drive, tail = ntpath.splitdrive(normalized)
            segments = tail.strip("\\/").lower().replace("/", "\\")
            forbidden = not segments or any(
                segments == name or segments.startswith(name + "\\")
                for name in ("windows", "program files", "program files (x86)", "programdata", "users\\public")
            )
        else:
            normalized = os.path.realpath(os.path.abspath(expanded))
            protected = ('/bin', '/sbin', '/etc', '/proc', '/sys', '/dev', '/run', '/var', '/usr')
            forbidden = normalized == '/' or any(
                normalized == path or normalized.startswith(path + '/') for path in protected
            )
        if forbidden and enforce_policy:
            raise ConfigValidationError('fileManagerRoots: 시스템 경로는 허용되지 않습니다.')
        if require_existing and not os.path.isdir(normalized):
            raise ConfigValidationError('fileManagerRoots: 존재하는 폴더 경로가 필요합니다.')
        if normalized not in result:
            result.append(normalized)
    return result


def _file_values(config: dict[str, Any]) -> dict[str, Any]:
    return {
        'fileManagerEnabled': parse_bool(config.get('fileManagerEnabled', True), 'fileManagerEnabled'),
        'fileManagerMode': str(config.get('fileManagerMode', 'blacklist')).strip().lower(),
        'fileManagerReadOnly': parse_bool(config.get('fileManagerReadOnly', False), 'fileManagerReadOnly'),
        'trashEnabled': parse_bool(config.get('trashEnabled', False), 'trashEnabled'),
        'fileManagerRoots': normalize_roots(config.get('fileManagerRoots', []), enforce_policy=False),
    }


def validate_transition(current: dict[str, Any], candidate: dict[str, Any], acknowledgement: str = '') -> None:
    before, after = _file_values(current), _file_values(candidate)
    risky = after['fileManagerEnabled'] and (
        after['fileManagerMode'] == 'blacklist'
        or not after['fileManagerReadOnly'] or not after['trashEnabled']
    )
    scope_changed = after['fileManagerEnabled'] and before['fileManagerRoots'] != after['fileManagerRoots']
    if (scope_changed or (risky and before != after)) and (not isinstance(acknowledgement, str) or acknowledgement.strip() != DANGER_ACK):
        raise ConfigValidationError('위험한 파일 관리자 설정을 적용하려면 확인 문구 ‘위험 설정 적용’을 입력하세요.')


def normalize_config_update(current: dict[str, Any], updates: Any, *, acknowledgement: str = '') -> dict[str, Any]:
    """Validate a partial update and return a new merged config, without writes.

    Known fields are typed strictly. Unknown extension settings are preserved for
    compatibility; transient form and confirmation fields are never persisted.
    """
    if not isinstance(updates, dict):
        raise ConfigValidationError('config: JSON 객체가 필요합니다.')
    result = {key: value for key, value in current.items() if key not in HELPER_FIELDS}
    for key, value in updates.items():
        if key in HELPER_FIELDS:
            continue
        if key in BOOL_FIELDS:
            value = parse_bool(value, key)
        elif key in INT_RANGES:
            if isinstance(value, bool) or not isinstance(value, (int, str)) or not re.fullmatch(r'[+-]?\d+', str(value).strip()):
                raise ConfigValidationError(f'{key}: 정수가 필요합니다.')
            value = int(value)
            low, high = INT_RANGES[key]
            if not low <= value <= high:
                raise ConfigValidationError(f'{key}: {low}~{high} 범위가 필요합니다.')
        elif key in {'plugin_type', 'fileManagerMode'}:
            allowed = {'basic', 'timemachine_plus'} if key == 'plugin_type' else {'whitelist', 'blacklist'}
            if not isinstance(value, str) or value.strip().lower() not in allowed:
                raise ConfigValidationError(f'{key}: 지원하지 않는 값입니다.')
            value = value.strip().lower()
        elif key == 'fileManagerRoots':
            value = normalize_roots(value, require_existing=True)
        elif key in STRING_FIELDS:
            if key == 'moveAfterProcessing' and value is None:
                value = ''
            if not isinstance(value, str) or '\x00' in value:
                raise ConfigValidationError(f'{key}: 문자열이 필요합니다.')
        result[key] = value
    # These are invariant in the supported personal deployment.
    result['loginMode'] = False
    result['fileManagerEnabled'] = True
    shift = result.get('timemachine_time_shift', 0)
    if result.get('plugin_type', 'basic') == 'basic':
        result['timemachine_time_shift'] = min(int(shift), 10)
    if not parse_bool(result.get('splitRecordingMode', False), 'splitRecordingMode'):
        result['splitOverlapSec'] = 0
        result['autoStopInterval'] = 0
    if not parse_bool(result.get('enableTray', False), 'enableTray'):
        result['minimizeToTrayOnClose'] = False
        result['minimizeToTrayOnStart'] = False
    validate_transition(current, result, acknowledgement)
    return result
