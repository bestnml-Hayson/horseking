#!/usr/bin/env python3
"""Validate config/model_profiles.json before it reaches any engine.

Run locally and in CI:
  python scripts/validate_config.py
Exit code 0 when every profile (including inherited) is structurally and
numerically sound, 1 otherwise.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from model_config import load_profiles, profile_names, validate_profiles


def main():
    raw = load_profiles()
    errors = validate_profiles(raw)
    if errors:
        print('[Config] INVALID')
        for err in errors:
            print(f'  - {err}')
        return 1
    names = profile_names(raw)
    default = raw.get('default_profile')
    print(f'[Config] OK - {len(names)} profiles, default={default}')
    print('  ' + ', '.join(names))
    return 0


if __name__ == '__main__':
    sys.exit(main())