char arr[4096];                       /* far under --data-model=large */
volatile short sink;

short index_of(const char *p)
{
    return (short)(p - arr);          /* the only line that matters */
}

int main(void)
{
    sink = index_of(arr + 3);
    return 0;
}
