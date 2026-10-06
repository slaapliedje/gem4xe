;;; B24's register form: src/vdi/vdi.c's vdi_v_opnvwk as cc65816 5.18.2
;;; compiled it at -O2 in a diagnostic build (phase 107).  `want` is put
;;; in _Dp/_Dp+2, an outlined fragment overwrites them, and `vdev = want`
;;; reads _Dp+8/_Dp+10 -- callee-saved registers this function pushed and
;;; never wrote, so it stores the CALLER's values.  mscan.unset_saved()
;;; must find both halves here.
vdi_v_opnvwk:
            pei     dp:.tiny (_Dp+8)
            pei     dp:.tiny (_Dp+10)
            phy
            phy
;      WORD i;
;      /* WHICH DEVICE, from work_in[0] -- the ST's ranges: 1..10 a screen,
;       * 21..30 a printer.  On the ST this is GDOS's business and it loads a
;       * driver; gem4xe has no GDOS by design (README) and both devices are
;       * already linked, so the id chooses between them here.
;       *
;       * That it is v_opnvwk rather than v_opnwk IS a departure, and a
;       * considered one: v_opnwk opens the PHYSICAL workstation, which on
;       * this machine is the screen the AES owns and everything is drawn
;       * on.  An application asking for a page must not reset that.  So a
;       * page is a virtual workstation on another device, which is exactly
;       * what a Vwk carrying its own device is for (src/vdi/vdi.h). */
;      WORD devid = (WORD)(contrl[3] > 0 ? intin[0] : 1);
            lda     ##0
            sec
            sbc     contrl+6
            bvc     `?L2284`
            eor     ##-32768
`?L2284`:   bmi     `?L1547`
            lda     ##1
            bra     `?L2895`
`?L1547`:
            lda     intin
`?L2895`:   sta     1,s
            lda     1,s
            sta     3,s
;      const VDIDEV FAR *want = (const VDIDEV FAR *)vwk_tab[0].dev;
            lda     vwk_tab+88
            sta     dp:.tiny _Dp
            lda     vwk_tab+90
            sta     dp:.tiny (_Dp+2)
;
;      for (i = 1; i < NUM_VWK; i++)
            lda     ##1
            sta     1,s
`?L386`:    lda     1,s
            sec
            sbc     ##4
            bvc     `?L2286`
            eor     ##-32768
`?L2286`:   bpl     `?L388`
;          if (vwk_tab[i].handle == 0)
            lda     1,s
            jsl     long:`?L3008`
            lda     vwk_tab,x
            bne     `?L387`
`?L388`:
;              break;
;      if (i == NUM_VWK) {
            lda     1,s
            cmp     ##4
            beq     `?L402`
;          contrl[6] = 0;
;          return;
;      }
;      if (devid >= 21 && devid <= 30) {
            lda     3,s
            sec
            sbc     ##21
            bvc     `?L2289`
            eor     ##-32768
`?L2289`:   bmi     `?L398`
            lda     ##30
            sec
            sbc     3,s
            bvc     `?L2291`
            eor     ##-32768
`?L2291`:   bmi     `?L398`
;          if (!pr_page_open()) {
            jsl     long:pr_page_open
            inc     a
            dec     a
            bne     `?L401`
`?L402`:
;              contrl[6] = 0;              /* no far memory for a page */
            stz     contrl+12
;              return;
            bra     `?L384`
`?L401`:
;          }
;          want = &vdev_print;
            lda     ##.word0 vdev_print
            sta     dp:.tiny _Dp
            lda     ##.word2 vdev_print
            sta     dp:.tiny (_Dp+2)
`?L398`:
;      }
;      vwk_tab[vwk_cur] = vwk;
            ldx     vwk_cur
            lda     ##92
            jsl     long:`?L2977`
;      vwk_cur = i;
            lda     1,s
            sta     vwk_cur
;      vdev = want;                        /* init_wk reads the extent off it */
            lda     dp:.tiny (_Dp+8)
            sta     vdev
            lda     dp:.tiny (_Dp+10)
            sta     vdev+2
;      init_wk((WORD)(i + 1));
            lda     1,s
            inc     a
            jsl     long:init_wk
;      vwk_tab[i] = vwk;
            lda     1,s
            ldx     ##92
            jsl     long:`?L2977`
;      vwk_own[i] = ctx_cur;           /* whoever asked keeps it */
            lda     1,s
            asl     a
            tax
            lda     ctx_cur
            sta     vwk_own,x
;      fill_workout();
            jsl     long:`?L3026`
