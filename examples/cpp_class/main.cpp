#include <iostream>
#include <supercode.hpp>

// A fixed-capacity LRU cache with int keys and double values.
super_class(LRUCache);

int main() {
    LRUCache c(2);
    c.put(1, 3.14);
    std::cout << c.get(1) << "\n";
    return 0;
}
