package main

import (
  "fmt"
  "os"
  "regexp"
  "io/ioutil"
  "strings"
  "strconv"
  "net/http"
  "time"
  "sort"

  "github.com/tealeg/xlsx"
)

type Log struct{
  Date    string
  /* Value   map[int]float64 */
  Value   [24]float64
}

type User struct{
  ID          string
  LPAR        string
  DateSerial  []string
  Logs        map[string][24]float64
}

type LPAR struct{
  ID          string
  Users       []User
  DateSerial  []string
}

var timeFormat string = "20060102"
var now = time.Now()

func (u *User) Dailylog (date string, ch chan<-Log) Log{
  daily := make(map[int]float64)
  baselink := "http://pkmfgvm4.pok.ibm.com/~PERFDOC/htbin/lnxulog?"
  target := fmt.Sprintf("12%s+%s+%s", u.LPAR, u.ID, date)
  /* fmt.Println(baselink+target) */
  resp, err := http.Get(baselink+target)
  if err != nil {
    fmt.Fprintf(os.Stderr, "fetch error: %v\n" ,err)
  }
  b, err := ioutil.ReadAll(resp.Body)
  resp.Body.Close()
  reCPU := regexp.MustCompile(`(?sU)Mean.*<hr>`)
  if reCPU.Match(b) {
    reData := regexp.MustCompile(`(\d+):\d+:\d+\s+(\d+\.\d*|\d+|\.\d+)`)
    CPU := reCPU.Find(b)
    r := strings.Split(string(CPU), "\r\n")
    for _, s := range r{
      if reData.MatchString(s) {
        data := reData.FindStringSubmatch(s)
        log, _ := strconv.ParseFloat(data[2], 64)
        clock, _ := strconv.ParseInt(data[1], 10, 0)
        daily[int(clock)] += log
      }
    }
  } else {
    fmt.Println("no data received!")
  }
  var aDaily [24]float64
  for k, v := range daily{
    if k != 23 || k != 0 {
      aDaily[k] = v/12
    } else if k == 23 {
      aDaily[k] = v/8
    } else if k == 0 {
      aDaily[k] = v/11
    }
    /* fmt.Printf("%v: %v\n", k, v) */
  }
  logentry := Log{date, aDaily}
  ch<-logentry
  /* fmt.Printf("%v:  ", date) */
  /* fmt.Println(time.Since(now).Seconds()) */
  return logentry
  /* fmt.Printf("%v\n", daily) */
}

func serDate (start, end string) []string{
  var dateSerial []string
  curD, _ := time.Parse(timeFormat, start)
  ed, _ := time.Parse(timeFormat, end)
  for ! curD.Equal(ed.AddDate(0,0,1)){
    dateSerial = append(dateSerial, curD.Format(timeFormat))
    curD = curD.AddDate(0,0,1)
  }
  return dateSerial
}

func (lpar *LPAR) getUsers () {
  baseLink := fmt.Sprintf("http://pkmfgvm4.pok.ibm.com/~PERFDOC/LNXVM%s.html", lpar.ID)
  userPat := regexp.MustCompile(`PKMFGVM4.POK.IBM.COM/~PERFDOC/([A-Z0-9]{8})`)
  resp, err := http.Get(baseLink)
  if err != nil {
    fmt.Fprintf(os.Stderr, "fetch error: %v\n" ,err)
  }
  b, err := ioutil.ReadAll(resp.Body)
  resp.Body.Close()
  if userPat.Match(b){
    var ul []string
    for _, u := range userPat.FindAllStringSubmatch(string(b), -1){
      ul = append(ul, u[1])
    }
    sort.Strings(ul)
    fmt.Println(ul)
    for _, u := range ul{
      user := User{
        ID: string(u),
        LPAR: lpar.ID,
        DateSerial: lpar.DateSerial,
        Logs: make(map[string][24]float64)}
      lpar.Users = append(lpar.Users, user)
      /* fmt.Println(lpar.Users) */
    }
  }
}

func perUser (u User){
  logChan := make(chan Log)
  for _, d := range u.DateSerial{
    go u.Dailylog(d, logChan)
  }
  for _ = range u.DateSerial{
    l := <-logChan
    /* fmt.Println(l.Date, l.Value) */
    u.Logs[l.Date] = l.Value
  }
}

func perLPAR(wb *xlsx.File, lparid string){
  ds := serDate("20170301", "20170331")
  var L LPAR
  L.ID = lparid
  ws,_:= wb.AddSheet("LNXVM" + L.ID)
  L.DateSerial = ds
  L.getUsers()
  /* fmt.Println(L.Users) */
  for _, u := range L.Users {
    fmt.Println("Processing User "+u.ID)
    perUser(u)
  }
  row := ws.AddRow()
  cell := row.AddCell()
  cell.Value="Date"
  cell = row.AddCell()
  cell.Value="Time"
  cell = row.AddCell()
  cell.Value="Total"
  for _, u := range L.Users{
    cell = row.AddCell()
    cell.Value = u.ID
  }
  for i, d := range ds{
    for t:=0; t<24; t++{
      line := (i+1)*(t+1)+1
      row = ws.AddRow()
      cell = row.AddCell()
      cell.Value = d           // Date
      cell = row.AddCell()
      if t > 9{
        cell.Value = strconv.Itoa(t)    // Time
      } else {
        cell.Value = "0" + strconv.Itoa(t)
      }

      num := len(L.Users)
      var endcol string
      if num < 23 {
        endcol = string(67 + num)
      } else{
        endcol = string(64 + num/26) + string(64+(num+3)%26)
      }
      /* sum := 0.0 */
      /* for _,u := range L.Users{ */
        /* sum += u.Logs[d][t] */
      /* } */

      cell = row.AddCell()
      /* cell.Value = fmt.Sprintf("%.2f", sum)           // Total */
      cell.SetFormula(fmt.Sprintf("SUM(D%d:%s%d)", line, endcol, line))           // Total
      for _, u := range L.Users{
        cell = row.AddCell()
        /* cell.Value = fmt.Sprintf("%.2f", u.Logs[d][t]) */
        fmtValue, _ := strconv.ParseFloat(fmt.Sprintf("%.2f", u.Logs[d][t]), 64)
        cell.SetFloat(fmtValue)
        /* cell.SetFloat(u.Logs[d][t]) */
    }

    }
  }

}

func main (){
  wb := xlsx.NewFile()
  list := []string{"33", "34", "64", "65", "67", "68", "69", "81"}
  /* list := []string{"81"} */
  for _, L := range list{
    perLPAR(wb, L)
  }

  err := wb.Save("file.xlsx")
  if err != nil {
    panic(err)
  }
  /* for _, u := range L.Users { */
    /* for _, d := range ds{ */
      /* fmt.Println(u.Logs[d]) */
    /* } */
  /* } */
}
