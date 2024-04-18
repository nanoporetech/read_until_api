#!/bin/bash

COMMON_INFO="/C=GB/S=Oxfordshire/L=Oxford/O=Oxford Nanopore Technologies plc/OU=MinKNOW RPCs Test Cert"

# Generate valid CA
openssl genrsa -passout pass:1234 -des3 -out ca.key 4096
openssl req -passin pass:1234 -new -x509 -days 2920 -key ca.key -out ca.crt -config ca.cnf

# Generate valid Key/Cert for localhost
openssl genrsa -passout pass:1234 -des3 -out localhost.key 4096
openssl req -passin pass:1234 -new -key localhost.key -out localhost.csr -config localhost.cnf
openssl x509 -req -passin pass:1234 -days 824 -in localhost.csr -CA ca.crt -CAkey ca.key -set_serial 01 -out localhost.crt
# Signing request is no longer required
rm localhost.csr

# Remove passphrase from the Key
openssl rsa -passin pass:1234 -in localhost.key -out localhost.key
