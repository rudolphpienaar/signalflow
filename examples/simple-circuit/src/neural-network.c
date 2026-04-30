#include <stdio.h>

void y1(int y1) { printf("%d", y1); }

void y2(int y2) { printf("%d", y2); }

void h1(int h1) {
  int h1v11, h1v12;
  y1(h1v11);
  y2(h1v12);
}

void h2(int h2) {
  int h2v21, h2v22;
  y1(h2v21);
  y2(h2v22);
}

void h3(int h3) {
  int h3v31, h3v32;
  y1(h3v31);
  y2(h3v32);
}

void x1(int x1) {
  int x1w11, x1w12, x1w13;
  h1(x1w11);
  h2(x1w12);
  h3(x1w13);
}

void x2(int x2) {
  int x2w21, x2w22, x2w23;
  h1(x2w21);
  h2(x2w22);
  h3(x2w23);
}

void x3(int x3) {
  int x3w31, x3w32, x3w33;
  h1(x3w31);
  h2(x3w32);
  h3(x3w33);
}

void x4(int x4) {
  int x4w41, x4w42, x4w43;
  h1(x4w41);
  h2(x4w42);
  h3(x4w43);
}
