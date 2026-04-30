#include <stdio.h>

int c1(int c1sig) {

  printf("hello!\n");

  return 1;
}

int c3(int c3sig) {

  int c3ret = c3(c3sig++);

  return 3;
}

int p2(int p2sig) {
  int c3ret;

  c3ret = c3(p2sig);
  return 1;
}

int c2(int c2sig) {

  int c1ret = c1(c2sig);
  int p2ret = p2(c1ret);

  return 2;
}

int ggc1(int input) {
  printf("hello1");

  return 0;
}

int gc1(int gc1sig);

int ggc2(int input) {

  int gc1ret;

  gc1ret = gc1(input);

  printf("hello1");

  return 0;
}

int ggc3(int input) {

  int ggcret;

  ggcret = ggc3(input);

  printf("hello1");

  return 0;
}

int gc1(int gc1sig) {
  int ggc1sig, ggc2sig, ggc3sig;
  int ggc1ret, ggc2ret, ggc3ret;

  ggc1ret = ggc1(ggc1sig);
  ggc2ret = ggc2(ggc2sig);
  ggc3ret = ggc3(ggc3sig);

  return 0;
}

int gc2(int gc2sig) {

  int ggc2ret;

  ggc2ret = ggc2(gc2sig);

  return 0;
}

int p1(void) {
  int c1sig, c2sig, c3sig;
  int c1ret, c2ret, c3ret;

  c1ret = c1(c1sig);
  c2ret = c2(c1ret);
  c3ret = c3(c2ret);

  return 1;
}
