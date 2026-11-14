COMMON_PASSWORDS = {
    '123456789012',
    '1234567890123',
    'qwerty123456',
    'password1234',
    'password12345',
    'letmein12345',
    'admin123456',
    'welcome12345',
}


def validate_new_password(password):
    if len(password) < 12:
        raise ValueError('Use at least 12 characters for a new password.')
    if len(password) > 128:
        raise ValueError('Password must be 128 characters or fewer.')
    if password.casefold() in COMMON_PASSWORDS:
        raise ValueError('Choose a less common password or passphrase.')
    return password
