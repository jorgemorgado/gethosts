# gethosts

## Description

Print host lists from the [GLPI](https://glpi-project.org/) inventory database.

## Installation

Nothing special here. Just copy the `gethosts` script into a directory in your
`$PATH` (usually, `/usr/local/bin`). Set the MySQL access:
```
DBSERVER = 'DBSERVER'
DBPORT   = 3306
DBUSER   = 'DBUSER'
DBPASS   = 'DBPASS'
DBNAME   = 'DBNAME'
```

If you use Bash completion, also copy the respective completion script into
`/etc/bash_completion`. Assuming this works, you will experience the full
power of `gethosts` - the completion uses itself to auto-complete your commands
in real-time.

If the given completion does not work on your system and, you manage to fix
the problem, please send me a pull-request.

## Usage

`gethosts` always outputs a list of hosts in a tabular format. The first column
is **always** the hostname. Additional columns can be specified with the `-f`
(field) option.

Other filters are also available. To check the available options use:
```
gethosts --help
```

Some examples:
```
# List all hosts from entity dev
gethosts --entity dev

# Also show thir OS name
gethosts --entity dev -f osname

# List all hosts from model ProLiant DL380 Gen9
gethosts --model "ProLiant DL380 Gen9"

# Also show their site (Linux only)
gethosts --model "ProLiant DL380 Gen9" -f site 'osname like "%linux%"'
```

## License

This repository is released under the [GPLv2 License](https://www.gnu.org/licenses/old-licenses/gpl-2.0.en.html).
