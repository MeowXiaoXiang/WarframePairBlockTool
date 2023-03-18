package main

import (
	"fmt"
	"image/color"
	"io/ioutil"
	"os"
	"os/exec"
	"strings"
	"syscall"

	"fyne.io/fyne/v2"
	"fyne.io/fyne/v2/app"
	"fyne.io/fyne/v2/canvas"
	"fyne.io/fyne/v2/container"
	"fyne.io/fyne/v2/dialog"
	"fyne.io/fyne/v2/layout"
	"fyne.io/fyne/v2/widget"
	"github.com/flopp/go-findfont"
)

func init() {
	fontPaths := findfont.List()
	for _, path := range fontPaths {
		fmt.Println(path)
		if strings.Contains(path, "msyh.ttc") {
			os.Setenv("FYNE_FONT", path)
			break
		}
	}
	fmt.Println("=============")
	fmt.Println("FYNE_FONT:", os.Getenv("FYNE_FONT"))
}

type config struct {
	statusLabel *fyne.Container
	portSelect  *widget.Select
	redButton   *fyne.Container
	greenButton *fyne.Container
	grayButton  *fyne.Container
}

var cfg config

func main() {
	app := app.New()
	win := app.NewWindow("WarframePairBlockTool")
	iconBytes, err := ioutil.ReadFile("WF.ico")
	if err != nil {
		dialog.ShowError(err, win)
		return
	}
	icon := fyne.NewStaticResource("icon", iconBytes)
	os.Unsetenv("FYNE_FONT")
	win.SetIcon(icon)
	// ------  label --------
	topLabel := widget.NewLabel("Warframe 配對限制器（強制主機）\n[ 封鎖 UDP 輸出 Port ]")
	topLabel.Alignment = fyne.TextAlignCenter
	// ------ status --------
	statusText := container.New(layout.NewCenterLayout(), canvas.NewText("初始化", color.NRGBA{R: 0, G: 0, B: 0, A: 255}))
	statusRect := canvas.NewRectangle(color.NRGBA{R: 200, G: 0, B: 200, A: 255})
	cfg.statusLabel = container.New(
		layout.NewMaxLayout(),
		statusRect,
		statusText,
	)
	// ------ label --------
	tipLabel := widget.NewLabel("請選擇您 Warframe 的 UDP 輸出 Port")
	tipLabel.Alignment = fyne.TextAlignCenter
	bottomLabel := widget.NewLabel("此工具為小翔製作\nDiscord：XiaoXiang_Meow#6647")
	bottomLabel.Alignment = fyne.TextAlignCenter
	// ------ select --------
	cfg.portSelect = widget.NewSelect(
		[]string{
			"4950 & 4955",
			"4960 & 4965",
			"4970 & 4975",
			"4980 & 4985",
			"4990 & 4995",
			"3074 & 3080",
		},
		func(value string) {
			fmt.Println("[DEBUG] Port 已被設定成：", value)
		},
	)
	cfg.portSelect.Alignment = fyne.TextAlignCenter
	cfg.portSelect.SetSelected("4950 & 4955")
	// -------- button -----------
	cfg.redButton = createButton("阻止配對[封鎖UDP輸出]", color.NRGBA{R: 255, G: 255, B: 255, A: 255}, color.NRGBA{R: 194, G: 14, B: 18, A: 255}, func() {
		fmt.Println("[DEBUG] 阻止配對按鈕被按下")
		if statusUpdate() == "0" {
			dialog.ShowInformation("Warning", "配對早已封鎖，請勿點按", win)
		} else {
			WFPORT := strings.Split(cfg.portSelect.Selected, " & ")
			cmd := exec.Command("netsh", "advfirewall", "firewall", "add", "rule", "name=WarframePairBlockPort", "protocol=UDP", "dir=out", "localport="+WFPORT[0]+"-"+WFPORT[1], "action=block")
			cmd.SysProcAttr = &syscall.SysProcAttr{HideWindow: true}
			err := cmd.Run()
			if err != nil {
				fmt.Println(err)
			}
			cmd = exec.Command("netsh", "advfirewall", "firewall", "set", "rule", "name=WarframePairBlockPort", "new", "enable=yes")
			cmd.SysProcAttr = &syscall.SysProcAttr{HideWindow: true}
			err = cmd.Run()
			if err != nil {
				fmt.Println("[Red Error] ", err)
			}
		}
		statusUpdate()
	})

	cfg.greenButton = createButton("恢復配對[恢復UDP輸出]", color.NRGBA{R: 0, G: 0, B: 0, A: 255}, color.NRGBA{R: 0, G: 205, B: 102, A: 255}, func() {
		fmt.Println("[DEBUG] 恢復配對被按下")
		if statusUpdate() == "1" {
			dialog.ShowInformation("Warning", "配對早已正常，請勿點按", win)
		} else {
			cmd := exec.Command("netsh", "advfirewall", "firewall", "delete", "rule", "name=WarframePairBlockPort")
			cmd.SysProcAttr = &syscall.SysProcAttr{HideWindow: true}
			if err := cmd.Run(); err != nil {
				fmt.Println("[Green Error] 移除防火牆規則失敗: \n", err)
				return
			}
		}
		statusUpdate()
	})

	cfg.grayButton = createButton("查看防火牆", nil, nil, func() {
		fmt.Println("[DEBUG] 開啟防火牆按鈕被按下")
		go openFirewall()
		statusUpdate()
	})

	vbox := container.NewVBox(
		topLabel,
		cfg.statusLabel,
		tipLabel,
		cfg.portSelect,
		cfg.grayButton,
		cfg.redButton,
		cfg.greenButton,
		bottomLabel,
	)
	win.SetContent(vbox)
	statusUpdate()
	win.CenterOnScreen()
	win.ShowAndRun()
}

func createButton(btnText string, textColor, btnColor color.Color, btnFunc func()) (content *fyne.Container) {
	text := canvas.NewText(btnText, textColor)
	btn := widget.NewButton("", btnFunc)
	rect := canvas.NewRectangle(btnColor)
	content = container.New(
		layout.NewMaxLayout(),
		rect,
		container.New(layout.NewCenterLayout(), text),
		btn,
	)
	return
}

func openFirewall() {
	cmd := exec.Command("mmc.exe", "wf.msc")
	cmd.SysProcAttr = &syscall.SysProcAttr{HideWindow: true}
	err := cmd.Run()
	if err != nil {
		fmt.Println("Error: ", err)
	}
}

func statusUpdate() string {
	cmd := exec.Command("netsh", "advfirewall", "firewall", "show", "rule", "name=WarframePairBlockPort", "dir=out")
	cmd.SysProcAttr = &syscall.SysProcAttr{HideWindow: true}
	err := cmd.Run()
	if exitErr, ok := err.(*exec.ExitError); ok && exitErr.ExitCode() == 1 {
		cfg.statusLabel.Objects[0].(*canvas.Rectangle).FillColor = color.NRGBA{R: 0, G: 205, B: 102, A: 255}
		label := cfg.statusLabel.Objects[1].(*fyne.Container).Objects[0].(*canvas.Text)
		label.Text = "目前狀態：配對目前正常"
		label.Color = color.NRGBA{R: 0, G: 0, B: 0, A: 255}
		cfg.statusLabel.Refresh()
		return "1"
	} else {
		cfg.statusLabel.Objects[0].(*canvas.Rectangle).FillColor = color.NRGBA{R: 194, G: 14, B: 18, A: 255}
		label := cfg.statusLabel.Objects[1].(*fyne.Container).Objects[0].(*canvas.Text)
		label.Text = "目前狀態：配對已阻斷"
		label.Color = color.NRGBA{R: 255, G: 255, B: 255, A: 255}
		cfg.statusLabel.Refresh()
		fmt.Println("目前狀態：配對已阻斷")
		return "0"
	}

}
