#!/bin/sh
export PATH=/tmp/armv7-eabihf--glibc--stable-2020.02-2/bin:$PATH
cd /tmp || exit 1
arm-buildroot-linux-gnueabihf-gcc --version | head -1
arm-buildroot-linux-gnueabihf-gcc -O2 -o eqt-b eqt.c -L. -l:libasound.so.2 -lm 2>&1 | head -5
arm-buildroot-linux-gnueabihf-gcc -O2 -o eqrelay-b eqrelay.c -L. -l:libasound.so.2 -lm 2>&1 | head -5
ls -la eqt-b eqrelay-b 2>/dev/null
echo "--- needed glibc ---"
arm-buildroot-linux-gnueabihf-objdump -T eqt-b 2>/dev/null | grep -o 'GLIBC_[0-9.]*' | sort -u | tail -3
