#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Usage:
#
#   gethosts -h
#
###########################################################################
# Print host lists from the GLPI inventory database.
# Copyright (c) 2012  Jorge Morgado
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.
###########################################################################
#
# History:
#
# v1.0, 20121228 Initial release
# v1.2, 20130120 Fix 'ip' and 'mac' lists
# v1.3, 20130121 Force itemtype to Computer on shared tables
#

"""A program to print hosts lists from the GLPI inventory database."""

__version__ = 1.3

import sys
import argparse
import shlex
import MySQLdb as mdb
from MySQLdb import cursors
import warnings

# treat MySQL warnings as errors
warnings.filterwarnings('error', category=mdb.Warning)

# Return codes
OK       = 0
WARNING  = 1
ERROR    = 2

version = """%(prog)s 1.3, Copyright(c), 2012"""
description = "Print lists of hosts from the GLPI inventory database."

# GLPI separates computers and other object types (e.g. NetworkEquipment,
# Peripheral, etc.) using physical tables. Although, some tables are used to
# store data from any object type (e.g. glpi_networkports). To ensure we only
# select Computers in this script, we need to force its type here.
itemtype = 'Computer'

# -----------------------------------------------------------------------------
# -- DON'T CHANGE ANYTHING BELOW THIS LINE UNLESS YOU KNOW WHAT YOU'RE DOING --

parser = argparse.ArgumentParser(description=description)

parser.add_argument('-v', '--version', action='version', version=version)

parser.add_argument('-d', '--debug', action='store_true', dest='debug',
                  default=False,
                  help='enable debug mode (developers only)',)

group = parser.add_argument_group('filter options')

group.add_argument('-l', action='store', dest='list',
                   choices=['osname', 'osver', 'site', 'domain',
                            'model', 'type', 'vendor',
                            'state', 'entity',
                            'user', 'group',
                            'software',
                            'ip', 'mac', 'netmask', 'subnet', 'gateway' ],
                   help='show list by name')
group.add_argument('--host', type=str, dest='hostname',
                   help='device hostname',)
group.add_argument('--osname', type=str, dest='osname',
                   help='operating system name',)
group.add_argument('--osver', type=str, dest='osver',
                   help='operating system version',)
group.add_argument('--site', type=str, dest='site',
                   help='host location',)
group.add_argument('--domain', type=str, dest='domain',
                   help='host domain',)
group.add_argument('--model', type=str, dest='model',
                   help='host hardware model',)
group.add_argument('--type', type=str, dest='type',
                   help='host hardware type',)
group.add_argument('--vendor', type=str, dest='vendor',
                   help='host vendor (manufacturer)',)
group.add_argument('--state', type=str, dest='state',
                   help='host state',)
group.add_argument('--entity', type=str, dest='entity',
                   help='host platform (entity)',)
group.add_argument('--user', type=str, dest='user',
                   help='host owner (user)',)
group.add_argument('--group', type=str, dest='group',
                   help='host department (group)',)
group.add_argument('--techuser', type=str, dest='techuser', metavar='TUSER',
                   help='host technical owner (user)',)
group.add_argument('--techgroup', type=str, dest='techgroup', metavar='TGROUP',
                   help='host technical department (group)',)
group.add_argument('--software', type=str, dest='software', metavar='SWNAME',
                   help='software name',)
group.add_argument('--mac', type=str, dest='mac',
                   help='host MAC address',)
group.add_argument('--ip', type=str, dest='ip',
                   help='host IP address',)
group.add_argument('--netmask', type=str, dest='netmask',
                   help='host netmask address',)
group.add_argument('--subnet', type=str, dest='subnet',
                   help='host subnet address',)
group.add_argument('--gateway', type=str, dest='gateway',
                   help='host default gateway address',)
group.add_argument('--case-sensitive', action='store_true', dest='binary',
                   default=False,
                   help='case sensite search (does not apply to expr filter)',)
group.add_argument(dest='expr', nargs=argparse.REMAINDER, metavar='expression',
                   help='filter criteria expression')

group = parser.add_argument_group('formatting options')
group.add_argument('-f', type=str, action='append', dest='field',
                   choices=['serial', 'uuid',
                            'osname', 'osver', 'site', 'domain',
                            'model', 'type', 'vendor',
                            'state', 'entity',
                            'user', 'group', 'techuser', 'techgroup',
                            'software', 'swver',
                            'ifname', 'mac',
                            'ip', 'netmask', 'subnet', 'gateway' ],
                   help='field to display (multiple options are allowed). ')
group.add_argument('-s', '--separator', dest='sep', default='\t',
                   help='output field separator (default is TAB)',)
group.add_argument('--no-sort', action='store_true', dest='nosort',
                   default=False,
                   help='do not sort the result',)
group.add_argument('--show-dups', action='store_true', dest='dups',
                   default=False,
                   help='show duplicates in the resulut (if any)',)
group.add_argument('--csv', action='store_true', dest='csv', default=False,
                   help='Comma Separated Values output (overrides -s unless '
                        'specified). If result has only one column, output '
                        'will be displayed on a single line.',)

args = parser.parse_args()

# Disable traceback if not in debug mode
if not args.debug:
    sys.tracebacklimit = 0

# MySQL read-only access
# mysql> GRANT SELECT ON $DBNAME.* TO $DBUSER@'*' IDENTIFIED BY '$DBPASS';
# mysql> FLUSH PRIVILEGES;
DBSERVER = 'DBSERVER'
DBPORT   = 3306
DBUSER   = 'DBUSER'
DBPASS   = 'DBPASS'
DBNAME   = 'DBNAME'

# Controls if the query will contain the software and/or network tables
has_software = False
has_network = False


def mysql_run(query, sep, csv):
    """Execute a MySQL query and print the result.
    By design, this function handles the MySQL connection, runs the argument
    query and prints the result in the proper format. Again, this is by design!
    The reason why we don't return the result to be printed outside it is
    mainly because the result set might be quite large, thus it is much more
    efficient to just print each line as we fetch the date from the database.
    """

    conn = None

    try:
        conn = mdb.connect(host=DBSERVER, port=DBPORT, db=DBNAME,
                           user=DBUSER, passwd=DBPASS, compress=1)
        cursor = conn.cursor(cursors.SSCursor)
        cursor.execute(query)

        # Overrite field separator if output in CSV
        if csv and sep == '\t': sep = ', '

        # Is first CSV row?
        first_csv = True

        # Print result using the cursor as iterator
        for row in cursor:
            # Is first column?
            first_col = True

            for col in row:
                # Make the first iteration a special case
                if first_col:
                    first_col = False
                else:
                    sys.stdout.write(sep)    # Print field separator

                # Use the field separator instead of newline
                if not first_csv: sys.stdout.write(sep)

                # Print NULL if column value is not defined
                sys.stdout.write(col if col else 'NULL')

            # If output in CSV and there is only one column
            if csv and len(row) == 1:
                if first_csv: first_csv = False
            else:
                sys.stdout.write('\n')

        # Final newline if output in CSV and there was only one column
        if csv and len(row) == 1: sys.stdout.write('\n')

        cursor.close()

    except mdb.Error, e:
        print "MySQL error %d: %s" % (e.args[0], e.args[1])
        return ERROR

    finally:
        if conn: conn.close()

    return OK


def parse_expression(expr, binary):
    """Parse an expression and converts it to some kind of SQL WHERE clause."""

    global has_software
    global has_network

    def add_softwares(field, binary):
        """Translate query field for softwares table."""

        global has_software; has_software = True
        return ' %ssw.%s' % (binary, field)

    def add_networkports(field, binary):
        """Translate query field for networkports table."""

        global has_network; has_network = True
        return ' %snp.%s' % (binary, field)

    fields = {
        'host':     lambda: ' %sc.name' % binary,   # Accept both host and
        'hostname': lambda: ' %sc.name' % binary,   # hostname
        'osname':   lambda: ' %sos.name' % binary,
        'osver':    lambda: ' %sosv.name' % binary,
        'site':     lambda: ' %sl.name' % binary,
        'domain':   lambda: ' %sd.name' % binary,
        'model':    lambda: ' %scm.name' % binary,
        'type':     lambda: ' %sct.name' % binary,
        'vendor':   lambda: ' %sm.name' % binary,
        'state':    lambda: ' %ss.name' % binary,
        'entity':   lambda: ' %se.name' % binary,
        'user':     lambda: ' %su.name' % binary,
        'group':    lambda: ' %sg.name' % binary,
        'techuser': lambda: ' %stu.name' % binary,
        'techgroup':lambda: ' %stg.name' % binary,
        'software': lambda: add_softwares('name', binary),
        'mac':      lambda: add_networkports('mac', binary),
        'ip':       lambda: add_networkports('ip', binary),
        'netmask':  lambda: add_networkports('netmask', binary),
        'subnet':   lambda: add_networkports('subnet', binary),
        'gateway':  lambda: add_networkports('gateway', binary),
        }

    FIELD   = 0
    OP      = 1
    LITERAL = 2
    CONDOP  = 3

    res = ''
    token = FIELD
    for i in list(shlex.shlex(expr)):
        if token == FIELD:
            try:
                # Try to translate the field in the expression by the DB field
                i = fields[i]()
                token = OP
            except:
                # If translateion fails, never mind... leave field as expressed
                sys.exc_clear()
        elif token == OP:
            if i != 'not':
                token = LITERAL
        elif token == LITERAL:
            # add quotes to the string if not there yet
            if not (i.startswith('"') or i.startswith("'")): i = "'%s" % i
            if not (i.endswith('"') or i.endswith("'")): i = "%s'" % i
            token = CONDOP
        elif token == CONDOP:
            token = FIELD;

        res += " %s" % i

    return "(%s )" % res


def main():
    """Parse arguments and run the respective query to GPLI."""

    global has_software
    global has_network

    def add_softwares(field, alias):
        """Add query field for softwares table."""

        global has_software; has_software = True
        return ', sw.%s as "%s"' % (field, alias)

    def add_softwareversions(field, alias):
        """Add query field for softwareversions table."""

        global has_software; has_software = True
        return ', sv.%s as "%s"' % (field, alias)

    def add_networkports(field, alias):
        """Add query field for networkports table."""

        global has_network; has_network = True
        return ', np.%s as "%s"' % (field, alias)

    def add_ipaddresses(field, alias):
        """Add query field for ipaddresses table."""

        global has_network; has_network = True
        return ', ip.%s as "%s"' % (field, alias)

    def add_ipnetworks(field, alias):
        """Add query field for ipaddresses table."""

        global has_network; has_network = True
        return ', ipn.%s as "%s"' % (field, alias)


    # Select distinct values if no duplicates
    if args.dups:
        query = 'select'
    else:
        query = 'select distinct'

    if args.list:
        # Build the list from the respective table
        if args.list in ['ip', 'mac', 'netmask', 'subnet', 'gateway']:
            query += ' %s from glpi_networkports where itemtype = "%s" and is_recursive = 0' % (args.list, itemtype)
        else:
            list = {
                'osname':   lambda: 'glpi_operatingsystems as t',
                'osver':    lambda: 'glpi_operatingsystemversions as t',
                'site':     lambda: 'glpi_locations as t',
                'domain':   lambda: 'glpi_domains as t',
                'model':    lambda: 'glpi_computermodels as t',
                'type':     lambda: 'glpi_computertypes as t',
                'vendor':   lambda: 'glpi_manufacturers as t',
                'state':    lambda: 'glpi_states as t',
                'entity':   lambda: 'glpi_entities as t',
                'user':     lambda: 'glpi_users as t',
                'group':    lambda: 'glpi_groups as t',
                'techuser': lambda: 'glpi_users as t',
                'techgroup':lambda: 'glpi_groups as t',
                'software': lambda: (' glpi_softwareversions as sv,'
                                     ' glpi_softwares as t'
                                     ' where sv.softwares_id = t.id'
                                       ' and t.is_deleted = 0'),
                }
            query += ' t.name from ' + list[args.list]()

    else:
        # At least the hostname must be always selected
        query += ' c.name as "name"'

        # Also select other fields if --field argument(s) have been provided
        if args.field:
            field = {
                'serial':   lambda: ', c.serial as "serial"',
                'uuid':     lambda: ', c.uuid as "uuid"',
                'osname':   lambda: ', os.name as "osname"',
                'osver':    lambda: ', osv.name as "osver"',
                'site':     lambda: ', l.name as "location"',
                'domain':   lambda: ', d.name as "domain"',
                'model':    lambda: ', cm.name as "model"',
                'type':     lambda: ', ct.name as "type"',
                'vendor':   lambda: ', m.name as "vendor"',
                'state':    lambda: ', s.name as "state"',
                'entity':   lambda: ', e.name as "entity"',
                'user':     lambda: ', u.name as "user"',
                'group':    lambda: ', g.name as "group"',
                'techuser': lambda: ', tu.name as "techuser"',
                'techgroup':lambda: ', tg.name as "techgroup"',
                'software': lambda: add_softwares('name', 'software'),
                'swver':    lambda: add_softwareversions('name', 'swver'),
                'ifname':   lambda: add_networkports('name', 'ifname'),
                'mac':      lambda: add_networkports('mac', 'mac'),
                #'ip':       lambda: add_networkports('ip', 'ip'),
                'ip':       lambda: add_ipaddresses('name', 'ip'),
                'netmask':  lambda: add_ipnetworks('netmask', 'netmask'),
                'subnet':   lambda: add_ipnetworks('address', 'subnet'),
                'gateway':  lambda: add_ipnetworks('gateway', 'gateway'),
                }
            for f in args.field:
                query += field[f]()

        # Set binary search if case-sensitive
        binary = 'binary ' if args.binary else ''

        # Next build the WHERE clause (do this before the FROM clause because
        # depending on the search criteria, the "has_ flags" will be set)
        where = ''
        if args.expr:
            where += ' and ' + parse_expression(" ".join(args.expr), binary)
        if args.hostname:
            where += " and %sc.name like '%s'" % (binary, args.hostname)
        if args.osname:
            where += " and %sos.name like '%s'" % (binary, args.osname)
        if args.osver:
            where += " and %sosv.name like '%s'" % (binary, args.osver)
        if args.site:
            where += " and %sl.name like '%s'" % (binary, args.site)
        if args.domain:
            where += " and %sd.name like '%s'" % (binary, args.domain)
        if args.model:
            where += " and %scm.name like '%s'" % (binary, args.model)
        if args.type:
            where += " and %sct.name like '%s'" % (binary, args.type)
        if args.vendor:
            where += " and %sm.name like '%s'" % (binary, args.vendor)
        if args.state:
            where += " and %ss.name like '%s'" % (binary, args.state)
        if args.entity:
            where += " and %se.name like '%s'" % (binary, args.entity)
        if args.user:
            where += " and %su.name like '%s'" % (binary, args.user)
        if args.group:
            where += " and %sg.name like '%s'" % (binary, args.group)
        if args.techuser:
            where += " and %stu.name like '%s'" % (binary, args.techuser)
        if args.techgroup:
            where += " and %stg.name like '%s'" % (binary, args.techgroup)
        if args.software:
            has_software = True
            where += " and %ssw.name like '%s'" % (binary, args.software)
        if args.ip:
            has_network = True
            where += " and %sip.name like '%s'" % (binary, args.ip)
        if args.mac:
            has_network = True
            where += " and %snp.mac like '%s'" % (binary, args.mac)
        if args.netmask:
            has_network = True
            where += " and %sipn.netmask like '%s'" % (binary, args.netmask)
        if args.subnet:
            has_network = True
            where += " and %sipn.address like '%s'" % (binary, args.subnet)
        if args.gateway:
            has_network = True
            where += " and %sipn.gateway like '%s'" % (binary, args.gateway)

        # Rock'n'roll the FROM clause                  table alias down here vvv
        query += (' from glpi_computers as c'                              # c
                  ' left join glpi_operatingsystems as os'                 # os
                       ' on (c.operatingsystems_id = os.id)'
                  ' left join glpi_operatingsystemversions as osv'         # osv
                       ' on (c.operatingsystemversions_id = osv.id)'
                  ' left join glpi_locations as l'                         # l
                       ' on (c.locations_id = l.id)'
                  ' left join glpi_domains as d'                           # d
                       ' on (c.domains_id = d.id)'
                  ' left join glpi_computermodels as cm'                   # cm
                       ' on (c.computermodels_id = cm.id)'
                  ' left join glpi_computertypes as ct'                    # ct
                       ' on (c.computertypes_id = ct.id)'
                  ' left join glpi_manufacturers as m'                     # m
                       ' on (c.manufacturers_id = m.id)'
                  ' left join glpi_states as s on (c.states_id = s.id)'    # s
                  ' left join glpi_entities as e'                          # e
                       ' on (c.entities_id = e.id)'
                  ' left join glpi_users as u on (c.users_id = u.id)'      # u
                  ' left join glpi_groups as g on (c.groups_id = g.id)'    # g
                  ' left join glpi_users as tu'                            # tu
                       ' on (c.users_id_tech = tu.id)'
                  ' left join glpi_groups as tg'                           # tg
                       ' on (c.groups_id_tech = tg.id)')
        if has_software:
            query += (' left join glpi_computers_softwareversions as csv'  # csv
                           ' on (c.id = csv.computers_id)'
                      ' left join glpi_softwareversions as sv'             # sv
                           ' on (csv.softwareversions_id = sv.id)'
                      ' left join glpi_softwares as sw'                    # sw
                           ' on (sv.softwares_id = sw.id)')
        if has_network:
            #query += (' left join glpi_networkports as np'                # np
            #query += (' left join glpi_networkportmigrations as np'       # np
            #               ' on (c.id = np.items_id)')
            query += (' left join glpi_networkports as np'                 # np
                            ' on (c.id = np.items_id)'
                      ' left join glpi_networknames as nn'                 # nn
                            ' on (np.id = nn.items_id)'
                      ' left join glpi_ipaddresses as ip'                  # ip
                           ' on (nn.id = ip.items_id)'
                      ' left join glpi_ipaddresses_ipnetworks as ian'      # ian
                           ' on (ip.id = ian.ipaddresses_id)'
                      ' left join glpi_ipnetworks as ipn'                  # ipn
                           ' on (ipn.id = ian.ipnetworks_id)')

        query += ' where c.is_deleted = 0'
        query += where

        if has_software: query += ' and csv.is_deleted = 0'
        if has_network:  query += ' and np.itemtype = "%s" and np.is_recursive = 0' % itemtype


    # Default is to sort by name
    if not args.nosort:
        query += ' order by name'

    # Show query if in debug mode
    if args.debug:
        print "SQL query: %s" % query

    return mysql_run(query, args.sep, args.csv)

if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print "Caught Ctrl-C."
        sys.exit(ERROR)
