program_uicc: program_uicc.c uicc.h milenage.h
	g++ --std=c++11 -g3 -I. -Wall program_uicc.c -o program_uicc

program_uicc_pcsc: program_uicc.c uicc.h milenage.h
	g++ --std=c++11 -g3 -DPCSC -I. -I/usr/include/PCSC  -Wall program_uicc.c  -L/lib/pcsc/drivers/ifd-ccid.bundle/Contents/Linux -lccid -o program_uicc_pcsc

clean:
	rm program_uicc program_uicc_pcsc
