#!/usr/bin/env python3
"""Analyze current combos and plan model replacements."""
import sys, json
sys.path.insert(0, 'd:\\omniroute-monetizer\\scripts\\automation')
from omniroute_api import OmniRouteAPI, save_json

api = OmniRouteAPI()
api.login()

combos = api.get_combos()

# Map each combo to its model requirements
plan = {}
for combo in combos:
    if not combo.get('name'):
        continue
    
    current_models = [m.get('model') for m in combo.get('models', [])]
    plan[combo['name']] = {
        'id': combo.get('id'),
        'current_models': current_models,
        'model_count': len(current_models),
        'strategy': '',
    }

# Define replacement strategy
replacements = {
    'frontier': {
        'strategy': 'best-of-breed multi-model routing',
        'models': [
            'agy/gemini-2.5-flash',           # Priority 1: fast, tool-safe
            'ainative/gpt-4o',                # Priority 2: reliable
            'ainative/claude-3-sonnet',       # Priority 3: fallback
        ]
    },
    'auto/best-coding': {
        'strategy': 'coding-optimized routing',
        'models': [
            'ainative/gpt-4o',                # Priority 1
            'agy/gemini-2.5-flash',           # Priority 2
            'ainative/claude-3-sonnet',       # Priority 3
        ]
    },
    'auto/best-reasoning': {
        'strategy': 'reasoning-optimized routing',
        'models': [
            'ainative/claude-3-sonnet',       # Priority 1: better reasoning
            'ainative/gpt-4o',                # Priority 2
            'agy/gemini-2.5-flash',           # Priority 3
        ]
    },
    'auto/best-chat': {
        'strategy': 'conversational routing',
        'models': [
            'ainative/gpt-4o-mini',           # Priority 1: fast, chatty
            'agy/gemini-2.5-flash-lite',      # Priority 2: lightweight
            'ainative/llama-3-3-70b',         # Priority 3: open-source option
        ]
    },
    'auto/pro-coding': {
        'strategy': 'premium coding routing',
        'models': [
            'ainative/gpt-4o',                # Priority 1
            'ainative/claude-3-sonnet',       # Priority 2
            'agy/gemini-2.5-flash',           # Priority 3
        ]
    },
    'auto/pro-reasoning': {
        'strategy': 'premium reasoning routing',
        'models': [
            'ainative/claude-3-sonnet',       # Priority 1
            'ainative/gpt-4o',                # Priority 2
            'agy/gemini-2.5-flash',           # Priority 3
        ]
    },
    'auto/pro-chat': {
        'strategy': 'premium conversational routing',
        'models': [
            'ainative/gpt-4o-mini',           # Priority 1
            'ainative/claude-3-sonnet',       # Priority 2
            'agy/gemini-2.5-flash-lite',      # Priority 3
        ]
    },
    'fusion-coder': {
        'strategy': 'fused coding routing',
        'models': [
            'ainative/gpt-4o',
            'agy/gemini-2.5-flash',
            'ainative/claude-3-sonnet',
        ]
    },
    'kimi-coding': {
        'strategy': 'alternative coding routing',
        'models': [
            'agy/gemini-2.5-flash',
            'ainative/gpt-4o',
            'ainative/claude-3-sonnet',
        ]
    },
    'moonshotai/kimi-k3-free': {
        'strategy': 'alternative free routing',
        'models': [
            'agy/gemini-2.5-flash-lite',
            'ainative/gpt-4o-mini',
            'ainative/llama-3-3-70b',
        ]
    },
}

print("[*] COMBO REPLACEMENT PLAN\n")
for name, new_config in replacements.items():
    old = plan.get(name, {})
    print(f"{name}:")
    print(f"  Current: {old.get('current_models')}")
    print(f"  Proposed: {new_config['models']}")
    print(f"  Strategy: {new_config['strategy']}")
    print()

save_json('replacement_plan.json', {
    'combos_to_update': replacements,
    'current_state': plan,
})

print("[+] Plan saved to state/replacement_plan.json")
