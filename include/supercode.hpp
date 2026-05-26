#ifndef SUPERCODE_HPP
#define SUPERCODE_HPP

#ifdef SUPERCODE_IDE

#ifndef super_class
#define super_class(name)
#endif

#ifndef super_import_func
#define super_import_func(name, return_type, ...) extern "C" return_type name(__VA_ARGS__)
#endif

#else

#ifndef SUPERCODE_RESOLVED
#error "SuperCode holes were not resolved. Build with `super`."
#endif

#ifndef super_class
#define super_class(name) \
    class name { \
    public: \
        explicit name(int capacity); \
        ~name(); \
        void put(int key, double value); \
        double get(int key) const; \
        bool contains(int key) const; \
    private: \
        struct Impl; \
        Impl* impl_; \
    }
#endif

#ifndef super_import_func
#define super_import_func(name, return_type, ...) extern "C" return_type name(__VA_ARGS__)
#endif

#endif

#endif
