#include <stdio.h>
#include <supercode.h>

// An int dynamic array with create, destroy, push, get, and size operations.
super_struct(IntVec);

int main(void) {
    IntVec *v = IntVec_create();
    IntVec_push(v, 1);
    IntVec_push(v, 2);
    printf("%d %d\n", IntVec_get(v, 0), IntVec_size(v));
    IntVec_destroy(v);
    return 0;
}
