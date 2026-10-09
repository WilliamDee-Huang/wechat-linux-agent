pango-null-guard.so: pango-null-guard.c
	$(CC) -shared -fPIC -O2 -o $@ $< -ldl

clean:
	rm -f pango-null-guard.so
