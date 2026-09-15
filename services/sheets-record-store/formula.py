"""Evaluate only the filtering expressions used by the existing sync services.

No Python eval and no remote execution. Unknown syntax fails closed.
"""
import re


TOKEN = re.compile(r"\s*(\{[^}]+\}|'(?:\\.|[^'\\])*'|[A-Za-z_]+|[(),=&])")


def matches(expression, fields):
    if not expression:
        return True
    tokens = []
    position = 0
    while position < len(expression):
        match = TOKEN.match(expression, position)
        if not match:
            raise ValueError('Unsupported filter expression')
        tokens.append(match.group(1))
        position = match.end()
    index = 0

    def take(expected=None):
        nonlocal index
        if index >= len(tokens):
            raise ValueError('Incomplete filter expression')
        token = tokens[index]
        index += 1
        if expected is not None and token != expected:
            raise ValueError('Invalid filter expression')
        return token

    def atom():
        token = take()
        if token.startswith('{'):
            return fields.get(token[1:-1], '')
        if token.startswith("'"):
            return re.sub(r'\\(.)', r'\1', token[1:-1])
        name = token.upper()
        take('(')
        args = []
        if index < len(tokens) and tokens[index] != ')':
            args.append(expr())
            while index < len(tokens) and tokens[index] == ',':
                take(',')
                args.append(expr())
        take(')')
        if name == 'FALSE' and not args:
            return False
        if name == 'TRUE' and not args:
            return True
        if name == 'AND':
            return all(args)
        if name == 'OR':
            return any(args)
        if name == 'NOT' and len(args) == 1:
            return not args[0]
        if name in ('LOWER', 'UPPER', 'TRIM') and len(args) == 1:
            return getattr(str(args[0]), {'LOWER':'lower','UPPER':'upper','TRIM':'strip'}[name])()
        if name == 'FIND' and len(args) == 2:
            return str(args[1]).find(str(args[0])) + 1
        raise ValueError('Unsupported filter function')

    def expr():
        value = atom()
        while index < len(tokens) and tokens[index] == '&':
            take('&')
            value = str(value) + str(atom())
        if index < len(tokens) and tokens[index] == '=':
            take('=')
            value = value == expr()
        return value

    result = expr()
    if index != len(tokens):
        raise ValueError('Trailing filter expression')
    return bool(result)
