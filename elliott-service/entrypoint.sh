#!/bin/bash
# Initialize Kerberos if keytab is mounted
if [ -f /etc/krb5/keytab/krb5.keytab ]; then
    echo "Initializing Kerberos..."
    kinit -kt /etc/krb5/keytab/krb5.keytab "${KRB5_PRINCIPAL:-art@IPA.REDHAT.COM}"
    echo "Kerberos ticket acquired."
fi

exec "$@"
