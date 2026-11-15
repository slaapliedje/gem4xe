/* f6_bank.c -- the banked half of src/f6_far.c (tests/emu/f6_far.py).
 *
 * Compiled into bank 1 with the allocator.  It puts and gets far memory
 * -- the helpers map a data bank into the window this code is running in
 * -- and then goes on computing here, which it can only do if the helpers
 * put this bank back.  0x1234 if all of that held.
 */
#include "portab.h"
#include "sys/farmem.h"

static uint8_t pattern(uint8_t i)
{
    return (uint8_t)(i ^ 0xA5);
}

uint16_t f6_banked(uint32_t at)
{
    uint8_t out[32], in[32];
    uint16_t sum = 0;
    uint8_t i;

    for (i = 0; i < 32; i++)
        out[i] = pattern(i);
    far_put(at, out, 32);
    far_get(in, at, 32);
    for (i = 0; i < 32; i++)            /* still this bank's code */
        sum = (uint16_t)(sum + (in[i] == pattern(i)));
    return sum == 32 ? 0x1234 : sum;
}
