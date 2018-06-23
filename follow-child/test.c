#include <stdlib.h>
#include <stdio.h>
#include <stdint.h>
#include <unistd.h>
#include <sys/fcntl.h>
#include <errno.h>

#ifndef COUNT
#define COUNT 1
#endif

void test() {
  puts(">> test()");
}

int main() {
  puts(">> main()");

  size_t count = 0;

  for (size_t i = 0; i < COUNT; i++) {
    int p = fork();
    if (p == 0) {
      printf("i am the child: %zu\n", count);
      test();
      break;
    } else {
      printf("i am the parent: %zu\n", count);
    }
    count++;
  }

  return 0;
}
