# Distributed Audio Over WiFi

## VS1053b CODEC

This is the normal operation mode of VS1053b. SDI data is decoded.
Decoded samples are converted to analog domain by the internal DAC.
If no decodable data is found, SCI_HDAT0 and SCI_HDAT1 are set to 0.

+----------+----------+----------+----------------------+
| Pad Name | LQFP Pin | Pin Type | Function             |
+----------+----------+----------+----------------------+
| RX   	   | 26       | DI       | UART receive         |
| TX   	   | 27       | DO       | UART transmit        |
| SCLK 		 | 28       | DI       | Clock for serial bus |
| SI       | 29       | DI       | Serial input         |
| SO       | 30       | DO3      | Serial output        |
+----------+----------+----------+----------------------+

If UART is not used, RX should be connected to IOVDD and TX be
unconnected.

https://cdn-shop.adafruit.com/datasheets/vs1053.pdf
